import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent, DragEvent, FormEvent, RefObject } from 'react';

type WorkflowState = 'idle' | 'loading' | 'success' | 'error';
type VerificationStatus = 'match' | 'review' | 'mismatch' | 'not_found';
type FieldName = 'brand_name' | 'class_type' | 'abv' | 'net_contents';

interface ApplicationValues {
  brand_name: string;
  class_type: string;
  abv: string;
  net_contents: string;
}

interface ExpectedApplicationData {
  brand_name: string;
  class_type: string;
  abv: number;
  net_contents: string;
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
}

interface FieldResult {
  field: FieldName;
  expected_raw: string;
  extracted_raw: string | null;
  expected_normalized: string | number;
  extracted_normalized: string | number | null;
  status: VerificationStatus;
  explanation: string;
  evidence: string[];
  similarity_score: number | null;
}

interface VerificationResponse {
  expected: ExpectedApplicationData;
  candidates: ExtractedCandidates;
  results: Record<FieldName, FieldResult>;
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

class VerificationRequestError extends Error {}

const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const INITIAL_VALUES: ApplicationValues = {
  brand_name: '',
  class_type: '',
  abv: '',
  net_contents: '',
};
const FIELD_LABELS: Record<FieldName, string> = {
  brand_name: 'Brand name',
  class_type: 'Class/type',
  abv: 'Alcohol content / ABV',
  net_contents: 'Net contents',
};
const STATUS_LABELS: Record<VerificationStatus, string> = {
  match: 'Match',
  review: 'Review',
  mismatch: 'Mismatch',
  not_found: 'Not found',
};

export function LabelOcrWorkflow() {
  const [application, setApplication] =
    useState<ApplicationValues>(INITIAL_VALUES);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [state, setState] = useState<WorkflowState>('idle');
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  useEffect(() => {
    if (state === 'error') errorRef.current?.focus();
    if (state === 'success') resultRef.current?.focus();
  }, [state]);

  function updateApplication(field: keyof ApplicationValues, value: string) {
    setApplication((current) => ({ ...current, [field]: value }));
    setResult(null);
    setError(null);
    setState('idle');
  }

  function chooseFile(file: File | undefined) {
    setResult(null);
    setError(null);
    setState('idle');
    if (!file) {
      updateSelectedFile(null);
      return;
    }
    if (!ACCEPTED_TYPES.includes(file.type)) {
      updateSelectedFile(null);
      setError('Choose a PNG, JPEG, or WebP image.');
      setState('error');
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      updateSelectedFile(null);
      setError('The image is too large. Choose a file smaller than 10 MB.');
      setState('error');
      return;
    }
    updateSelectedFile(file);
  }

  function updateSelectedFile(file: File | null) {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    const objectUrl = file ? URL.createObjectURL(file) : null;
    previewUrlRef.current = objectUrl;
    setPreviewUrl(objectUrl);
    setSelectedFile(file);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    chooseFile(event.target.files?.[0]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (event.dataTransfer.files.length !== 1) {
      updateSelectedFile(null);
      setResult(null);
      setError('Drop exactly one label image.');
      setState('error');
      return;
    }
    chooseFile(event.dataTransfer.files[0]);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setError('Choose one label image before verifying the label.');
      setState('error');
      return;
    }
    if (Object.values(application).some((value) => !value.trim())) {
      setError('Enter all four application fields before verifying the label.');
      setState('error');
      return;
    }

    setError(null);
    setResult(null);
    setState('loading');
    const formData = new FormData();
    formData.append('brand_name', application.brand_name);
    formData.append('class_type', application.class_type);
    formData.append('abv', application.abv);
    formData.append('net_contents', application.net_contents);
    formData.append('file', selectedFile);

    try {
      const response = await fetch('/api/labels/verify', {
        method: 'POST',
        body: formData,
      });
      const payload: unknown = await readJson(response);
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
      setResult(payload);
      setState('success');
    } catch (requestError) {
      setError(
        requestError instanceof VerificationRequestError
          ? requestError.message
          : 'The verification service could not be reached. Check the connection and try again.',
      );
      setState('error');
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <ol className="review-steps" aria-label="Label verification workflow">
        <li>
          <section className="step-card" aria-labelledby="application-title">
            <StepHeading number="1" id="application-title">
              Application data
            </StepHeading>
            <p>
              Enter values from the application. Capitalization does not need to
              match the label.
            </p>
            <div className="application-fields">
              <TextField
                id="brand-name"
                label="Brand name"
                value={application.brand_name}
                placeholder="Stone's Throw"
                onChange={(value) => updateApplication('brand_name', value)}
                disabled={state === 'loading'}
              />
              <TextField
                id="class-type"
                label="Class/type designation"
                value={application.class_type}
                placeholder="Kentucky Straight Bourbon Whiskey"
                onChange={(value) => updateApplication('class_type', value)}
                disabled={state === 'loading'}
              />
              <TextField
                id="abv"
                label="Alcohol content / ABV (%)"
                value={application.abv}
                placeholder="45"
                type="number"
                step="0.1"
                min="0.1"
                max="100"
                onChange={(value) => updateApplication('abv', value)}
                disabled={state === 'loading'}
              />
              <TextField
                id="net-contents"
                label="Net contents"
                value={application.net_contents}
                placeholder="750 mL"
                onChange={(value) => updateApplication('net_contents', value)}
                disabled={state === 'loading'}
              />
            </div>
          </section>
        </li>

        <li>
          <section className="step-card" aria-labelledby="upload-title">
            <StepHeading number="2" id="upload-title">
              Label image
            </StepHeading>
            <p>
              Choose one PNG, JPEG, or WebP image. It is processed for this
              request and not retained.
            </p>
            <div
              className="upload-area"
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleDrop}
              data-testid="upload-drop-zone"
            >
              <label className="file-label" htmlFor="label-image">
                Choose label image
              </label>
              <input
                id="label-image"
                className="file-picker"
                type="file"
                accept={ACCEPTED_TYPES.join(',')}
                onChange={handleFileChange}
                disabled={state === 'loading'}
                aria-describedby="upload-guidance"
              />
              <p id="upload-guidance">
                Choose a file or drag and drop it here. Maximum 10 MB.
              </p>
            </div>
            {selectedFile && (
              <div className="selected-image">
                {previewUrl && (
                  <img
                    src={previewUrl}
                    alt={`Preview of selected label: ${selectedFile.name}`}
                  />
                )}
                <div>
                  <p className="selected-file-name">{selectedFile.name}</p>
                  <p className="selected-file-size">
                    {formatFileSize(selectedFile.size)}
                  </p>
                </div>
              </div>
            )}
          </section>
        </li>

        <li className="action-step">
          <section className="step-card" aria-labelledby="verify-title">
            <StepHeading number="3" id="verify-title">
              Verify label
            </StepHeading>
            <p>
              Run local OCR once, then compare the four application fields with
              extracted label evidence.
            </p>
            {error && (
              <div
                className="workflow-error"
                role="alert"
                tabIndex={-1}
                ref={errorRef}
              >
                <strong>Verification could not be completed</strong>
                <p>{error}</p>
              </div>
            )}
            <button
              className="primary-button"
              type="submit"
              disabled={state === 'loading'}
            >
              {state === 'loading' ? 'Verifying label…' : 'Verify Label'}
            </button>
            {state === 'loading' && (
              <p className="loading-status" role="status" aria-live="polite">
                Running local OCR and comparing application fields.
              </p>
            )}
          </section>
        </li>

        <li className="results-step">
          <section className="step-card" aria-labelledby="results-title">
            <StepHeading number="4" id="results-title">
              Verification results
            </StepHeading>
            <p>
              These informational results support manual review; they are not a
              regulatory decision.
            </p>
            {result ? (
              <VerificationResults result={result} resultRef={resultRef} />
            ) : (
              <div className="placeholder results-placeholder">
                <p>No verification has been performed.</p>
                <p>
                  Enter application data, choose an image, then select “Verify
                  Label.”
                </p>
              </div>
            )}
          </section>
        </li>
      </ol>
    </form>
  );
}

function StepHeading({
  number,
  id,
  children,
}: {
  number: string;
  id: string;
  children: string;
}) {
  return (
    <div className="step-heading">
      <span className="step-number" aria-hidden="true">
        {number}
      </span>
      <h2 id={id}>{children}</h2>
    </div>
  );
}

function TextField({
  id,
  label,
  value,
  placeholder,
  onChange,
  disabled,
  type = 'text',
  ...numberProps
}: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  disabled: boolean;
  type?: 'text' | 'number';
  step?: string;
  min?: string;
  max?: string;
}) {
  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        name={id}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        required
        {...numberProps}
      />
    </div>
  );
}

function VerificationResults({
  result,
  resultRef,
}: {
  result: VerificationResponse;
  resultRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className="verification-result" tabIndex={-1} ref={resultRef}>
      <div className="overall-summary" role="status" aria-live="polite">
        <strong>{result.overall_summary}</strong>
      </div>
      <div className="field-results">
        {(Object.keys(FIELD_LABELS) as FieldName[]).map((field) => {
          const fieldResult = result.results[field];
          return (
            <article
              className={`field-result status-${fieldResult.status}`}
              key={field}
            >
              <div className="field-result-heading">
                <h3>{FIELD_LABELS[field]}</h3>
                <span className="status-label">
                  {STATUS_LABELS[fieldResult.status]}
                </span>
              </div>
              <dl>
                <div>
                  <dt>Expected</dt>
                  <dd>{fieldResult.expected_raw}</dd>
                </div>
                <div>
                  <dt>Detected</dt>
                  <dd>{fieldResult.extracted_raw ?? 'Not detected'}</dd>
                </div>
              </dl>
              <p>{fieldResult.explanation}</p>
            </article>
          );
        })}
      </div>
      <details className="ocr-evidence">
        <summary>Inspect raw OCR evidence</summary>
        <div className="result-summary" aria-label="OCR processing details">
          <span>
            Completed in {formatDuration(result.total_verification_duration_ms)}
          </span>
          <span>OCR: {formatDuration(result.ocr_duration_ms)}</span>
          <span>Engine: {result.engine}</span>
          <span>
            Image: {result.image.width} × {result.image.height}{' '}
            {result.image.format}
          </span>
        </div>
        {result.warnings.length > 0 && (
          <div className="ocr-warning">
            <strong>Evidence warnings</strong>
            <ul>
              {result.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
        <pre className="raw-text">
          {result.raw_text || 'No text was detected in this image.'}
        </pre>
      </details>
    </div>
  );
}

function isVerificationResponse(
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
    typeof candidate.results !== 'object' ||
    candidate.results === null
  ) {
    return false;
  }
  return (Object.keys(FIELD_LABELS) as FieldName[]).every((field) => {
    const result = candidate.results?.[field];
    return (
      typeof result === 'object' &&
      result !== null &&
      ['match', 'review', 'mismatch', 'not_found'].includes(result.status) &&
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

function formatDuration(durationMs: number): string {
  return durationMs < 1_000
    ? `${Math.round(durationMs)} ms`
    : `${(durationMs / 1_000).toFixed(1)} s`;
}

function formatFileSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
