import { describe, expect, it } from 'vitest';
import {
  BATCH_CSV_HEADERS,
  MAX_BATCH_SIZE,
  batchResultsCsv,
  deriveBatchItemStatus,
  mapBatchFiles,
  normalizeFilename,
  parseBatchCsv,
  runBoundedQueue,
} from './batchVerification';
import type { MappedBatchItem } from './batchVerification';
import type { VerificationResponse, VerificationStatus } from './verification';

const HEADER = BATCH_CSV_HEADERS.join(',');

function row(filename = 'label.jpg') {
  return `${filename},"Stone's Throw",Bourbon Whiskey,45,750 mL,Example Distillery,"Louisville, KY",false,`;
}

describe('batch CSV parsing and mapping', () => {
  it('parses quoted commas, escaped quotes, CRLF, BOM, and blank optional values', () => {
    const csv = `\uFEFF${HEADER}\r\nlabel.jpg,"The ""Best"" Brand",Gin,40,1 L,Example LLC,"Miami, FL",false,\r\n`;
    const parsed = parseBatchCsv(csv);

    expect(parsed.errors).toEqual([]);
    expect(parsed.records).toHaveLength(1);
    expect(parsed.records[0]?.application).toMatchObject({
      brand_name: 'The "Best" Brand',
      producer_address: 'Miami, FL',
      imported_product: false,
      country_origin: '',
    });
  });

  it('reports missing required columns instead of accepting a partial manifest', () => {
    const parsed = parseBatchCsv('image_filename,brand_name\nlabel.jpg,Brand');

    expect(parsed.records).toEqual([]);
    expect(parsed.errors.join(' ')).toContain('Missing required columns');
  });

  it('reports invalid row values and imported-country requirements', () => {
    const parsed = parseBatchCsv(
      `${HEADER}\nlabel.jpg,Brand,Gin,101,ounces,Producer,Address,true,`,
    );

    expect(parsed.records[0]?.errors).toEqual(
      expect.arrayContaining([
        expect.stringContaining('abv'),
        expect.stringContaining('net_contents'),
        expect.stringContaining('country_origin'),
      ]),
    );
  });

  it('attaches malformed quoted-row errors to that item without hiding other rows', () => {
    const parsed = parseBatchCsv(
      `${HEADER}\n${row('valid.jpg')}\nbad.jpg,"unterminated,Gin,40,750 mL,Producer,Address,false,`,
    );

    expect(parsed.records[0]?.errors).toEqual([]);
    expect(parsed.records[1]?.errors.join(' ')).toContain('CSV parsing error');
  });

  it('flags duplicate filenames after conservative path, case, and Unicode normalization', () => {
    const parsed = parseBatchCsv(
      `${HEADER}\n${row('C:\\labels\\Café.JPG')}\n${row('cafe\u0301.jpg')}`,
    );

    expect(parsed.records).toHaveLength(2);
    expect(
      parsed.records.every((record) =>
        record.errors.join(' ').includes('Duplicate'),
      ),
    ).toBe(true);
    expect(normalizeFilename(' C:\\labels\\Café.JPG ')).toBe('café.jpg');
  });

  it('reports missing, duplicate, unsupported, and unmatched image files', () => {
    const parsed = parseBatchCsv(
      `${HEADER}\n${row('one.jpg')}\n${row('missing.jpg')}`,
    );
    const mapping = mapBatchFiles(parsed.records, [
      image('ONE.JPG'),
      image('one.jpg'),
      image('extra.jpg'),
    ]);

    expect(mapping.items[0]?.errors.join(' ')).toContain(
      'Multiple selected images',
    );
    expect(mapping.items[1]?.errors.join(' ')).toContain('No selected image');
    expect(mapping.unmatchedFiles).toEqual(['extra.jpg']);
  });

  it('rejects manifests over the 300-record maximum without truncating', () => {
    const rows = Array.from({ length: MAX_BATCH_SIZE + 1 }, (_, index) =>
      row(`${index}.jpg`),
    );
    const parsed = parseBatchCsv([HEADER, ...rows].join('\n'));

    expect(parsed.records).toEqual([]);
    expect(parsed.errors.join(' ')).toContain('maximum batch size is 300');
  });
});

describe('bounded batch execution and results', () => {
  it('keeps a 300-item queue at two concurrent requests and isolates one failure', async () => {
    let active = 0;
    let maximum = 0;
    const results = await runBoundedQueue(
      Array.from({ length: 300 }, (_, index) => index),
      async (value) => {
        active += 1;
        maximum = Math.max(maximum, active);
        await new Promise((resolve) => setTimeout(resolve, 2));
        active -= 1;
        if (value === 3) throw new Error('bad item');
        return value * 2;
      },
      { concurrency: 2 },
    );

    expect(maximum).toBe(2);
    expect(
      results.filter((result) => result.status === 'fulfilled'),
    ).toHaveLength(299);
    expect(results[3]?.status).toBe('rejected');
  });

  it('stops scheduling new work while allowing current workers to settle', async () => {
    let stop = false;
    const results = await runBoundedQueue(
      [0, 1, 2, 3, 4],
      async (value) => {
        stop = true;
        return value;
      },
      { concurrency: 2, shouldStop: () => stop },
    );

    expect(
      results.filter((result) => result.status === 'fulfilled'),
    ).toHaveLength(1);
    expect(
      results.filter((result) => result.status === 'skipped'),
    ).toHaveLength(4);
  });

  it('uses mismatch over review/not-found and review over match', () => {
    expect(
      deriveBatchItemStatus(
        response({ brand_name: 'mismatch', abv: 'review' }),
      ),
    ).toBe('mismatch');
    expect(deriveBatchItemStatus(response({ abv: 'not_found' }))).toBe(
      'review',
    );
    expect(deriveBatchItemStatus(response({}))).toBe('match');
  });

  it('exports concise CSV with quoted values, field statuses, duration, and errors', () => {
    const item = {
      id: 'row-2',
      rowNumber: 2,
      imageFilename: 'label.jpg',
      application: {
        brand_name: '=DANGEROUS(), LLC',
        class_type: 'Gin',
        abv: '40',
        net_contents: '750 mL',
        producer_name: 'Producer',
        producer_address: 'Miami, FL',
        imported_product: false,
        country_origin: '',
      },
      errors: [],
      file: null,
      status: 'match',
      result: response({}),
      processingError: null,
    } satisfies MappedBatchItem;

    const csv = batchResultsCsv([item]);
    expect(csv).toContain('government_warning_status');
    expect(csv).toContain("'=DANGEROUS(), LLC");
    expect(csv).toContain('label.jpg');
    expect(csv).toContain('1234');
  });
});

function image(name: string, type = 'image/jpeg') {
  return new File(['image'], name, { type });
}

function response(
  overrides: Partial<Record<string, VerificationStatus>>,
): VerificationResponse {
  const fields = [
    'brand_name',
    'class_type',
    'abv',
    'net_contents',
    'producer_name',
    'producer_address',
    'country_origin',
  ] as const;
  const results = Object.fromEntries(
    fields.map((field) => [
      field,
      {
        field,
        expected_raw: 'Expected',
        extracted_raw: 'Detected',
        expected_normalized: 'expected',
        extracted_normalized: 'detected',
        status:
          overrides[field] ??
          (field === 'country_origin' ? 'not_applicable' : 'match'),
        explanation: 'Explanation',
        evidence: [],
        similarity_score: null,
      },
    ]),
  ) as unknown as VerificationResponse['results'];
  return {
    results,
    government_warning: {
      overall_status: overrides.government_warning ?? 'match',
    },
    total_verification_duration_ms: 1234,
  } as VerificationResponse;
}
