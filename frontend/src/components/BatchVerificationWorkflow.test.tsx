import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BatchVerificationWorkflow } from './BatchVerificationWorkflow';

const HEADER =
  'image_filename,brand_name,class_type,abv,net_contents,producer_name,producer_address,imported_product,country_origin';

describe('batch verification workflow', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:batch-csv'),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(
      () => undefined,
    );
  });

  it('imports a valid CSV, maps multiple images, and submits the existing verification API', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse());
    vi.stubGlobal('fetch', fetchMock);
    render(<BatchVerificationWorkflow />);

    await loadManifest(
      `${HEADER}\nfirst.png,First Brand,Gin,40,750 mL,First LLC,"Miami, FL",false,\n` +
        'second.png,Second Brand,Vodka,45,1 L,Second LLC,"Austin, TX",false,',
    );
    selectImages([image('first.png'), image('second.png')]);

    expect(await screen.findByText('First Brand')).toBeVisible();
    expect(screen.getByText('Second Brand')).toBeVisible();
    expect(screen.getAllByText('Ready')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Verify Batch' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Batch summary')).toBeVisible();
    expect(screen.getAllByText('All checks matched').length).toBeGreaterThan(0);
    const submitted = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(submitted.get('brand_name')).toBe('First Brand');
    expect(submitted.get('file')).toBeInstanceOf(File);
  });

  it('isolates a failed item and retries only that item', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okResponse())
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: { message: 'The image could not be processed.' },
          }),
          { status: 500, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(okResponse());
    vi.stubGlobal('fetch', fetchMock);
    render(<BatchVerificationWorkflow />);

    await loadManifest(
      `${HEADER}\ngood.png,Good Brand,Gin,40,750 mL,Good LLC,"Miami, FL",false,\n` +
        'bad.png,Bad Brand,Vodka,45,1 L,Bad LLC,"Austin, TX",false,',
    );
    selectImages([image('good.png'), image('bad.png')]);
    fireEvent.click(screen.getByRole('button', { name: 'Verify Batch' }));

    expect(
      (await screen.findAllByText('Processing failed')).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText('The image could not be processed.').length,
    ).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Retry failed items' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'Retry failed items' }),
      ).not.toBeInTheDocument(),
    );
  });

  it('shows mapping problems and downloads template and result CSV files', async () => {
    render(<BatchVerificationWorkflow />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Download CSV template' }),
    );
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);

    await loadManifest(
      `${HEADER}\nmissing.png,"Brand, LLC",Gin,40,750 mL,Producer,"Miami, FL",false,`,
    );
    selectImages([image('extra.png')]);

    expect(
      await screen.findByText(/No selected image matches missing.png/),
    ).toBeVisible();
    expect(screen.getByText('Images not represented in the CSV')).toBeVisible();
    expect(screen.getByText('extra.png')).toBeVisible();
  });

  it('keeps an invalid row visible while processing a valid mapped row', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse());
    vi.stubGlobal('fetch', fetchMock);
    render(<BatchVerificationWorkflow />);

    await loadManifest(
      `${HEADER}\nvalid.png,Valid Brand,Gin,40,750 mL,Valid LLC,"Miami, FL",false,\n` +
        'invalid.png,Invalid Brand,Vodka,999,bad units,Invalid LLC,"Austin, TX",false,',
    );
    selectImages([image('valid.png'), image('invalid.png')]);

    expect(await screen.findAllByText('Invalid')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Verify Batch' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(
      screen.getAllByText(/abv must be greater than 0/).length,
    ).toBeGreaterThan(0);
  });
});

async function loadManifest(contents: string) {
  const manifest = new File([contents], 'applications.csv', {
    type: 'text/csv',
  });
  Object.defineProperty(manifest, 'text', {
    value: vi.fn().mockResolvedValue(contents),
  });
  fireEvent.change(screen.getByLabelText('Choose application CSV'), {
    target: { files: [manifest] },
  });
  await screen.findByText('Selected: applications.csv');
}

function selectImages(files: File[]) {
  fireEvent.change(screen.getByLabelText('Choose label images'), {
    target: { files },
  });
}

function image(name: string) {
  return new File(['image'], name, { type: 'image/png' });
}

function okResponse() {
  return new Response(JSON.stringify(successfulPayload()), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function successfulPayload() {
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
        extracted_raw: field === 'country_origin' ? null : 'Detected',
        expected_normalized: 'expected',
        extracted_normalized: field === 'country_origin' ? null : 'detected',
        status: field === 'country_origin' ? 'not_applicable' : 'match',
        explanation: 'The field matches.',
        evidence: [],
        similarity_score: null,
      },
    ]),
  );
  const check = {
    status: 'match',
    explanation: 'The warning check matches.',
    evidence: [],
    measurements: {},
  };
  return {
    expected: {},
    candidates: {},
    results,
    government_warning: {
      overall_status: 'match',
      localized_text: null,
      source_lines: [],
      bounding_box: null,
      mean_ocr_confidence: 0.95,
      analysis_duration_ms: 10,
      checks: {
        presence: check,
        wording: check,
        heading_capitalization: check,
        heading_boldness: check,
        body_not_bold: check,
        continuous_statement: check,
        separation: check,
        legibility_contrast: check,
        type_size: check,
        characters_per_inch: check,
      },
    },
    overall_summary: 'All checked application fields match the label.',
    raw_text: 'Detected text',
    engine: 'tesseract-cli',
    total_verification_duration_ms: 400,
    ocr_duration_ms: 300,
    warnings: [],
    image: { width: 800, height: 400, format: 'PNG' },
  };
}
