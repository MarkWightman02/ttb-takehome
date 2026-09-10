export type VerificationStatus =
  'match' | 'review' | 'mismatch' | 'not_found' | 'not_applicable';

export type FieldName =
  | 'brand_name'
  | 'class_type'
  | 'abv'
  | 'net_contents'
  | 'producer_name'
  | 'producer_address'
  | 'country_origin';

export interface ApplicationValues {
  brand_name: string;
  class_type: string;
  abv: string;
  net_contents: string;
  producer_name: string;
  producer_address: string;
  imported_product: boolean;
  country_origin: string;
}

interface ExpectedApplicationData {
  brand_name: string;
  class_type: string;
  abv: number;
  net_contents: string;
  producer_name: string;
  producer_address: string;
  imported_product: boolean;
  country_origin: string | null;
}

interface TextCandidate {
  raw_value: string;
  normalized_value: string;
  source_line: string;
  line_number: number;
}

interface NumericCandidate {
  raw_value: string;
  source_line: string;
  line_number: number;
}

interface ExtractedCandidates {
  brand_name: TextCandidate[];
  class_type: TextCandidate[];
  abv: (NumericCandidate & { normalized_percent: number })[];
  net_contents: (NumericCandidate & { normalized_ml: number })[];
  producer_name: TextCandidate[];
  producer_address: TextCandidate[];
  country_origin: TextCandidate[];
}

export type WarningCheckName =
  | 'presence'
  | 'wording'
  | 'heading_capitalization'
  | 'heading_boldness'
  | 'body_not_bold'
  | 'continuous_statement'
  | 'separation'
  | 'legibility_contrast'
  | 'type_size'
  | 'characters_per_inch';

interface WarningCheck {
  status: VerificationStatus;
  explanation: string;
  evidence: string[];
  measurements: Record<string, string | number | boolean | null>;
}

export interface GovernmentWarningAnalysis {
  overall_status: VerificationStatus;
  localized_text: string | null;
  source_lines: string[];
  bounding_box: {
    left: number;
    top: number;
    width: number;
    height: number;
    coordinate_space: 'preprocessed_image';
  } | null;
  mean_ocr_confidence: number | null;
  analysis_duration_ms: number;
  checks: Record<WarningCheckName, WarningCheck>;
}

export interface FieldResult {
  field: FieldName;
  expected_raw: string;
  extracted_raw: string | null;
  expected_normalized: string | number | null;
  extracted_normalized: string | number | null;
  status: VerificationStatus;
  explanation: string;
  evidence: string[];
  similarity_score: number | null;
}

export interface VerificationResponse {
  expected: ExpectedApplicationData;
  candidates: ExtractedCandidates;
  results: Record<FieldName, FieldResult>;
  government_warning: GovernmentWarningAnalysis;
  overall_summary: string;
  raw_text: string;
  engine: string;
  total_verification_duration_ms: number;
  ocr_duration_ms: number;
  warnings: string[];
  image: {
    width: number;
    height: number;
    format: 'PNG' | 'JPEG' | 'WEBP';
  };
}

interface ApiErrorResponse {
  error?: { message?: string };
}

export class VerificationRequestError extends Error {}

const FIELD_NAMES: FieldName[] = [
  'brand_name',
  'class_type',
  'abv',
  'net_contents',
  'producer_name',
  'producer_address',
  'country_origin',
];
export const VERIFICATION_REQUEST_TIMEOUT_MS = 15_000;

export function buildVerificationFormData(
  application: ApplicationValues,
  file: File,
): FormData {
  const formData = new FormData();
  formData.append('brand_name', application.brand_name);
  formData.append('class_type', application.class_type);
  formData.append('abv', application.abv);
  formData.append('net_contents', application.net_contents);
  formData.append('producer_name', application.producer_name);
  formData.append('producer_address', application.producer_address);
  formData.append('imported_product', String(application.imported_product));
  if (application.imported_product) {
    formData.append('country_origin', application.country_origin);
  }
  formData.append('file', file);
  return formData;
}

export async function verifyLabel(
  application: ApplicationValues,
  file: File,
): Promise<VerificationResponse> {
  const formData = buildVerificationFormData(application, file);
  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    VERIFICATION_REQUEST_TIMEOUT_MS,
  );

  let response: Response;
  try {
    response = await fetch('/api/labels/verify', {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
  } catch {
    if (controller.signal.aborted) {
      throw new VerificationRequestError(
        'Verification timed out. Try the label again.',
      );
    }
    throw new VerificationRequestError(
      'The verification service could not be reached. Check the connection and try again.',
    );
  } finally {
    window.clearTimeout(timeout);
  }

  const payload = await readJson(response);
  if (!response.ok) {
    const apiError = payload as ApiErrorResponse;
    throw new VerificationRequestError(
      apiError.error?.message ??
        'The label could not be verified. Try another image.',
    );
  }
  if (!isVerificationResponse(payload)) {
    throw new VerificationRequestError(
      'The server returned an unexpected verification response.',
    );
  }
  return payload;
}

export function isVerificationResponse(
  payload: unknown,
): payload is VerificationResponse {
  if (typeof payload !== 'object' || payload === null) return false;
  const candidate = payload as Partial<VerificationResponse>;
  if (
    typeof candidate.overall_summary !== 'string' ||
    typeof candidate.raw_text !== 'string' ||
    typeof candidate.engine !== 'string' ||
    typeof candidate.total_verification_duration_ms !== 'number' ||
    typeof candidate.ocr_duration_ms !== 'number' ||
    typeof candidate.government_warning !== 'object' ||
    candidate.government_warning === null ||
    typeof candidate.results !== 'object' ||
    candidate.results === null
  ) {
    return false;
  }
  return FIELD_NAMES.every((field) => {
    const result = candidate.results?.[field];
    return (
      typeof result === 'object' &&
      result !== null &&
      ['match', 'review', 'mismatch', 'not_found', 'not_applicable'].includes(
        result.status,
      ) &&
      typeof result.explanation === 'string'
    );
  });
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}
