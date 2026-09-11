import Papa from 'papaparse';
import {
  automatedWarningStatus,
  manualPhysicalConfirmationRequired,
} from './verification';
import type {
  ApplicationValues,
  FieldName,
  VerificationResponse,
  VerificationStatus,
} from './verification';

export const MAX_BATCH_SIZE = 300;
export const BATCH_CONCURRENCY = 2;
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_IMAGE_TYPES = [
  'image/png',
  'image/jpeg',
  'image/webp',
] as const;
export const BATCH_CSV_HEADERS = [
  'image_filename',
  'brand_name',
  'class_type',
  'abv',
  'net_contents',
  'producer_name',
  'producer_address',
  'imported_product',
  'country_origin',
] as const;

export type BatchItemStatus =
  | 'invalid'
  | 'ready'
  | 'queued'
  | 'processing'
  | 'match'
  | 'review'
  | 'mismatch'
  | 'processing_error'
  | 'cancelled';

export interface BatchManifestRecord {
  id: string;
  rowNumber: number;
  imageFilename: string;
  application: ApplicationValues;
  errors: string[];
}

export interface BatchParseResult {
  records: BatchManifestRecord[];
  errors: string[];
}

export interface MappedBatchItem extends BatchManifestRecord {
  file: File | null;
  status: BatchItemStatus;
  result: VerificationResponse | null;
  processingError: string | null;
}

export interface BatchMapping {
  items: MappedBatchItem[];
  unmatchedFiles: string[];
  errors: string[];
}

export interface QueueResult<Result> {
  status: 'fulfilled' | 'rejected' | 'skipped';
  value?: Result;
  reason?: unknown;
}

const VOLUME_PATTERN =
  /^\s*\d+(?:\.\d+)?\s*(?:ml|millilit(?:er|re)s?|l|lit(?:er|re)s?|pints?|pt|fl\.?\s*oz\.?|fluid\s+ounces?)\s*$/i;
const FIELD_NAMES: FieldName[] = [
  'brand_name',
  'class_type',
  'abv',
  'net_contents',
  'producer_name',
  'producer_address',
  'country_origin',
];

export function parseBatchCsv(csv: string): BatchParseResult {
  const parsed = Papa.parse<Record<string, string>>(csv, {
    header: true,
    skipEmptyLines: 'greedy',
    transformHeader: (header) => header.replace(/^\uFEFF/, '').trim(),
  });
  const fields = parsed.meta.fields ?? [];
  const missing = BATCH_CSV_HEADERS.filter(
    (header) => !fields.includes(header),
  );
  const unexpected = fields.filter(
    (header) =>
      !BATCH_CSV_HEADERS.includes(header as (typeof BATCH_CSV_HEADERS)[number]),
  );
  const errors: string[] = [];
  if (missing.length)
    errors.push(`Missing required columns: ${missing.join(', ')}.`);
  if (unexpected.length)
    errors.push(`Unexpected columns: ${unexpected.join(', ')}.`);
  if (new Set(fields).size !== fields.length) {
    errors.push('The CSV contains duplicate column names.');
  }
  errors.push(
    ...parsed.errors
      .filter((error) => error.row === undefined)
      .map((error) => `CSV: ${error.message}`),
  );
  if (
    missing.length ||
    unexpected.length ||
    new Set(fields).size !== fields.length
  ) {
    return { records: [], errors };
  }
  if (parsed.data.length > MAX_BATCH_SIZE) {
    errors.push(
      `The manifest contains ${parsed.data.length} records; the maximum batch size is ${MAX_BATCH_SIZE}.`,
    );
    return { records: [], errors };
  }

  const records = parsed.data.map((row, index) => parseRow(row, index + 2));
  for (const error of parsed.errors) {
    if (error.row === undefined) continue;
    records[error.row]?.errors.push(`CSV parsing error: ${error.message}`);
  }
  const byFilename = new Map<string, BatchManifestRecord[]>();
  for (const record of records) {
    const normalized = normalizeFilename(record.imageFilename);
    if (!normalized) continue;
    const matches = byFilename.get(normalized) ?? [];
    matches.push(record);
    byFilename.set(normalized, matches);
  }
  for (const matches of byFilename.values()) {
    if (matches.length < 2) continue;
    for (const record of matches) {
      record.errors.push(
        `Duplicate image filename after safe normalization: ${record.imageFilename}.`,
      );
    }
  }
  if (!records.length && !errors.length)
    errors.push('The CSV does not contain any records.');
  return { records, errors };
}

function parseRow(
  row: Record<string, string>,
  rowNumber: number,
): BatchManifestRecord {
  const value = (name: (typeof BATCH_CSV_HEADERS)[number]) =>
    String(row[name] ?? '').trim();
  const imageFilename = value('image_filename');
  const importedText = value('imported_product').toLocaleLowerCase('en-US');
  const importedProduct = importedText === 'true';
  const application: ApplicationValues = {
    brand_name: value('brand_name'),
    class_type: value('class_type'),
    abv: value('abv'),
    net_contents: value('net_contents'),
    producer_name: value('producer_name'),
    producer_address: value('producer_address'),
    imported_product: importedProduct,
    country_origin: value('country_origin'),
  };
  const errors: string[] = [];
  const required: [string, string][] = [
    ['image_filename', imageFilename],
    ['brand_name', application.brand_name],
    ['class_type', application.class_type],
    ['abv', application.abv],
    ['net_contents', application.net_contents],
    ['producer_name', application.producer_name],
    ['producer_address', application.producer_address],
  ];
  for (const [name, fieldValue] of required) {
    if (!fieldValue) errors.push(`${name} is required.`);
  }
  const abv = Number(application.abv);
  if (application.abv && (!Number.isFinite(abv) || abv <= 0 || abv > 100)) {
    errors.push('abv must be greater than 0 and no more than 100.');
  }
  if (
    application.net_contents &&
    !VOLUME_PATTERN.test(application.net_contents)
  ) {
    errors.push(
      'net_contents must use mL, L, US pint, or US fluid ounce units.',
    );
  }
  if (importedText !== 'true' && importedText !== 'false') {
    errors.push('imported_product must be true or false.');
  }
  if (importedProduct && !application.country_origin) {
    errors.push('country_origin is required when imported_product is true.');
  }
  return {
    id: `row-${rowNumber}`,
    rowNumber,
    imageFilename,
    application,
    errors,
  };
}

export function mapBatchFiles(
  records: BatchManifestRecord[],
  files: File[],
): BatchMapping {
  const errors: string[] = [];
  if (files.length > MAX_BATCH_SIZE) {
    errors.push(
      `You selected ${files.length} images; the maximum batch size is ${MAX_BATCH_SIZE}.`,
    );
  }
  const filesByName = new Map<string, File[]>();
  for (const file of files) {
    const normalized = normalizeFilename(file.name);
    const matches = filesByName.get(normalized) ?? [];
    matches.push(file);
    filesByName.set(normalized, matches);
  }
  const manifestNames = new Set(
    records.map((record) => normalizeFilename(record.imageFilename)),
  );
  const unmatchedFiles = files
    .filter((file) => !manifestNames.has(normalizeFilename(file.name)))
    .map((file) => file.name);

  const items = records.map((record) => {
    const itemErrors = [...record.errors];
    const normalized = normalizeFilename(record.imageFilename);
    const matches = filesByName.get(normalized) ?? [];
    let file: File | null = null;
    if (matches.length === 0 && normalized) {
      itemErrors.push(`No selected image matches ${record.imageFilename}.`);
    } else if (matches.length > 1) {
      itemErrors.push(
        `Multiple selected images match ${record.imageFilename}.`,
      );
    } else if (matches.length === 1) {
      file = matches[0]!;
      const fileError = validateImageFile(file);
      if (fileError) itemErrors.push(fileError);
    }
    return {
      ...record,
      errors: itemErrors,
      file,
      status: itemErrors.length ? 'invalid' : 'ready',
      result: null,
      processingError: null,
    } satisfies MappedBatchItem;
  });
  return { items, unmatchedFiles, errors };
}

export function normalizeFilename(value: string): string {
  const basename =
    value.normalize('NFC').trim().replaceAll('\\', '/').split('/').pop() ?? '';
  return basename.trim().toLocaleLowerCase('en-US');
}

export function validateImageFile(file: File): string | null {
  if (
    !ACCEPTED_IMAGE_TYPES.includes(
      file.type as (typeof ACCEPTED_IMAGE_TYPES)[number],
    )
  ) {
    return `${file.name} is not a PNG, JPEG, or WebP image.`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `${file.name} is larger than 10 MB.`;
  }
  return null;
}

export function deriveBatchItemStatus(
  result: VerificationResponse,
): BatchItemStatus {
  const statuses: VerificationStatus[] = [
    ...FIELD_NAMES.map((field) => result.results[field].status),
    automatedWarningStatus(result.government_warning),
  ];
  if (statuses.includes('mismatch')) return 'mismatch';
  if (
    statuses.some((status) => status === 'review' || status === 'not_found')
  ) {
    return 'review';
  }
  return 'match';
}

export function batchIssueSummary(result: VerificationResponse): string {
  const issues = FIELD_NAMES.filter((field) => {
    const status = result.results[field].status;
    return (
      status === 'mismatch' || status === 'review' || status === 'not_found'
    );
  }).map(
    (field) => `${field.replaceAll('_', ' ')}: ${result.results[field].status}`,
  );
  if (automatedWarningStatus(result.government_warning) !== 'match') {
    issues.push(
      `government warning: ${automatedWarningStatus(result.government_warning)}`,
    );
  }
  const summary = issues.length
    ? issues.join('; ')
    : 'All automated checks matched.';
  return manualPhysicalConfirmationRequired(result.government_warning)
    ? `${summary} Manual physical confirmation required.`
    : summary;
}

export async function runBoundedQueue<Item, Result>(
  items: Item[],
  worker: (item: Item, index: number) => Promise<Result>,
  options: {
    concurrency?: number;
    shouldStop?: () => boolean;
    onStart?: (item: Item, index: number) => void;
    onSettled?: (
      result: QueueResult<Result>,
      item: Item,
      index: number,
    ) => void;
  } = {},
): Promise<QueueResult<Result>[]> {
  const concurrency = Math.max(
    1,
    Math.floor(options.concurrency ?? BATCH_CONCURRENCY),
  );
  const results: QueueResult<Result>[] = Array(items.length);
  let nextIndex = 0;
  async function consume() {
    while (nextIndex < items.length) {
      if (options.shouldStop?.()) break;
      const index = nextIndex++;
      const item = items[index]!;
      options.onStart?.(item, index);
      try {
        const value = await worker(item, index);
        results[index] = { status: 'fulfilled', value };
      } catch (reason) {
        results[index] = { status: 'rejected', reason };
      }
      options.onSettled?.(results[index]!, item, index);
    }
  }
  const consumers = Array.from(
    { length: Math.min(concurrency, items.length) },
    () => consume(),
  );
  await Promise.all(consumers);
  for (let index = 0; index < items.length; index += 1) {
    if (!results[index]) results[index] = { status: 'skipped' };
  }
  return results;
}

export function batchResultsCsv(items: MappedBatchItem[]): string {
  const rows = items.map((item) => ({
    image_filename: item.imageFilename,
    brand_name: item.application.brand_name,
    overall_status: exportStatus(item),
    brand_status: item.result?.results.brand_name.status ?? '',
    class_type_status: item.result?.results.class_type.status ?? '',
    abv_status: item.result?.results.abv.status ?? '',
    net_contents_status: item.result?.results.net_contents.status ?? '',
    producer_name_status: item.result?.results.producer_name.status ?? '',
    producer_address_status: item.result?.results.producer_address.status ?? '',
    country_origin_status: item.result?.results.country_origin.status ?? '',
    government_warning_status:
      item.result?.government_warning.overall_status ?? '',
    automated_warning_status: item.result
      ? automatedWarningStatus(item.result.government_warning)
      : '',
    manual_physical_confirmation_required: item.result
      ? manualPhysicalConfirmationRequired(item.result.government_warning)
      : '',
    duration_ms: item.result
      ? Math.round(item.result.total_verification_duration_ms)
      : '',
    error: item.processingError ?? item.errors.join(' '),
  }));
  return Papa.unparse(rows, { newline: '\r\n', escapeFormulae: true });
}

function exportStatus(item: MappedBatchItem): string {
  if (item.status === 'invalid') return 'validation_error';
  return item.status;
}

export const BATCH_TEMPLATE_CSV = Papa.unparse(
  [
    {
      image_filename: 'example-label.jpg',
      brand_name: "Stone's Throw",
      class_type: 'Kentucky Straight Bourbon Whiskey',
      abv: '45',
      net_contents: '750 mL',
      producer_name: 'Example Distillery LLC',
      producer_address: 'Louisville, KY',
      imported_product: 'false',
      country_origin: '',
    },
  ],
  { columns: [...BATCH_CSV_HEADERS], newline: '\r\n' },
);
