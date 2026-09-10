import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent, DragEvent, FormEvent, RefObject } from 'react';
import { VerificationRequestError, verifyLabel } from '../verification';
import type {
  ApplicationValues,
  FieldName,
  GovernmentWarningAnalysis,
  VerificationResponse,
  VerificationStatus,
  WarningCheckName,
} from '../verification';

type WorkflowState = 'idle' | 'loading' | 'success' | 'error';

const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const INITIAL_VALUES: ApplicationValues = {
  brand_name: '',
  class_type: '',
  abv: '',
  net_contents: '',
  producer_name: '',
  producer_address: '',
  imported_product: false,
  country_origin: '',
};
const FIELD_LABELS: Record<FieldName, string> = {
  brand_name: 'Brand name',
  class_type: 'Class/type',
  abv: 'Alcohol content / ABV',
  net_contents: 'Net contents',
  producer_name: 'Producer / bottler name',
  producer_address: 'Producer / bottler address',
  country_origin: 'Country of origin',
};
const STATUS_LABELS: Record<VerificationStatus, string> = {
  match: 'Match',
  review: 'Review',
  mismatch: 'Mismatch',
  not_found: 'Not found',
  not_applicable: 'Not applicable',
};
const STATUS_COUNT_LABELS: Record<VerificationStatus, string> = {
  match: 'matched',
  review: 'review',
  mismatch: 'mismatched',
  not_found: 'not found',
  not_applicable: 'not applicable',
};
const WARNING_CHECK_LABELS: Record<WarningCheckName, string> = {
  presence: 'Warning found',
  wording: 'Required wording',
  heading_capitalization: '“GOVERNMENT WARNING” capitalization',
  heading_boldness: 'Heading boldness',
  body_not_bold: 'Body text not bold',
  continuous_statement: 'Continuous statement',
  separation: 'Separation / layout',
  legibility_contrast: 'Legibility / contrasting background',
  type_size: 'Type-size requirement',
  characters_per_inch: 'Maximum characters per inch',
};
const WARNING_CHECK_GROUPS: {
  id: string;
  title: string;
  description: string;
  checks: WarningCheckName[];
}[] = [
  {
    id: 'warning-text-checks',
    title: 'Deterministic text checks',
    description: 'Direct checks against the wording recognized by OCR.',
    checks: ['presence', 'wording', 'heading_capitalization'],
  },
  {
    id: 'warning-image-checks',
    title: 'Image-based evidence',
    description:
      'Conservative signals from OCR location, layout, weight, and contrast.',
    checks: [
      'heading_boldness',
      'body_not_bold',
      'continuous_statement',
      'separation',
      'legibility_contrast',
    ],
  },
  {
    id: 'warning-physical-checks',
    title: 'Manual physical confirmation',
    description:
      'A digital image without trustworthy scale cannot establish physical measurements.',
    checks: ['type_size', 'characters_per_inch'],
  },
];

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

  function updateImportedProduct(imported: boolean) {
    setApplication((current) => ({
      ...current,
      imported_product: imported,
      country_origin: imported ? current.country_origin : '',
    }));
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
    const requiredValues = [
      application.brand_name,
      application.class_type,
      application.abv,
      application.net_contents,
      application.producer_name,
      application.producer_address,
    ];
    if (
      requiredValues.some((value) => !value.trim()) ||
      (application.imported_product && !application.country_origin.trim())
    ) {
      setError(
        'Enter all required application fields before verifying the label.',
      );
      setState('error');
      return;
    }

    setError(null);
    setResult(null);
    setState('loading');
    try {
      const payload = await verifyLabel(application, selectedFile);
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
              <TextField
                id="producer-name"
                label="Producer / bottler name"
                value={application.producer_name}
                placeholder="Old Tom Distillery LLC"
                onChange={(value) => updateApplication('producer_name', value)}
                disabled={state === 'loading'}
              />
              <TextField
                id="producer-address"
                label="Producer / bottler address"
                value={application.producer_address}
                placeholder="Louisville, KY"
                onChange={(value) =>
                  updateApplication('producer_address', value)
                }
                disabled={state === 'loading'}
              />
              <fieldset className="import-control">
                <legend>Imported product</legend>
                <label>
                  <input
                    type="radio"
                    name="imported-product"
                    value="no"
                    checked={!application.imported_product}
                    onChange={() => updateImportedProduct(false)}
                    disabled={state === 'loading'}
                  />
                  No
                </label>
                <label>
                  <input
                    type="radio"
                    name="imported-product"
                    value="yes"
                    checked={application.imported_product}
                    onChange={() => updateImportedProduct(true)}
                    disabled={state === 'loading'}
                  />
                  Yes
                </label>
              </fieldset>
              {application.imported_product && (
                <TextField
                  id="country-origin"
                  label="Country of origin"
                  value={application.country_origin}
                  placeholder="France"
                  onChange={(value) =>
                    updateApplication('country_origin', value)
                  }
                  disabled={state === 'loading'}
                />
              )}
            </div>
          </section>
        </li>

        <li>
          <section className="step-card" aria-labelledby="upload-title">
            <StepHeading number="2" id="upload-title">
              Submitted label artwork
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
              Run local OCR, then compare the application fields with extracted
              label evidence.
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
              Review results
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

export function VerificationResults({
  result,
  resultRef,
  idPrefix = '',
}: {
  result: VerificationResponse;
  resultRef?: RefObject<HTMLDivElement | null>;
  idPrefix?: string;
}) {
  const statusCounts = (Object.keys(FIELD_LABELS) as FieldName[]).reduce(
    (counts, field) => {
      counts[result.results[field].status] += 1;
      return counts;
    },
    {
      match: 0,
      review: 0,
      mismatch: 0,
      not_found: 0,
      not_applicable: 0,
    } satisfies Record<VerificationStatus, number>,
  );

  return (
    <div className="verification-result" tabIndex={-1} ref={resultRef}>
      <div className="overall-summary" role="status" aria-live="polite">
        <strong>{result.overall_summary}</strong>
        <p aria-label="Application field status counts">
          {formatStatusCounts(statusCounts)}
        </p>
      </div>
      <div className="field-results" aria-label="Application field results">
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
                  <dd>
                    {fieldResult.status === 'not_applicable'
                      ? 'Not applicable'
                      : (fieldResult.extracted_raw ?? 'Not detected')}
                  </dd>
                </div>
              </dl>
              <p>{fieldResult.explanation}</p>
            </article>
          );
        })}
      </div>
      <GovernmentWarningResults
        warning={result.government_warning}
        idPrefix={idPrefix}
      />
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

function GovernmentWarningResults({
  warning,
  idPrefix,
}: {
  warning: GovernmentWarningAnalysis;
  idPrefix: string;
}) {
  const warningTitleId = `${idPrefix}government-warning-title`;
  const automatedChecksPassed = Object.entries(warning.checks)
    .filter(([name]) => name !== 'type_size' && name !== 'characters_per_inch')
    .every(([, check]) => check.status === 'match');
  return (
    <section
      className="government-warning-results"
      aria-labelledby={warningTitleId}
    >
      <div className="warning-section-heading">
        <h3 id={warningTitleId}>Government Health Warning</h3>
        <span className={`status-label status-${warning.overall_status}`}>
          {STATUS_LABELS[warning.overall_status]}
        </span>
      </div>
      {automatedChecksPassed && (
        <p>
          Automated warning checks passed; physical dimensions require manual
          confirmation.
        </p>
      )}
      <p className="warning-limit-note">
        Text checks compare OCR wording directly. Image evidence can flag likely
        presentation issues. Physical type size and characters per inch require
        a trustworthy scale.
      </p>
      {WARNING_CHECK_GROUPS.map((group) => {
        const groupId = `${idPrefix}${group.id}`;
        return (
          <section
            className="warning-check-group"
            aria-labelledby={groupId}
            key={group.id}
          >
            <h4 id={groupId}>{group.title}</h4>
            <p>{group.description}</p>
            <div className="warning-checks">
              {group.checks.map((name) => {
                const check = warning.checks[name];
                return (
                  <article
                    className={`warning-check status-${check.status}`}
                    key={name}
                  >
                    <div className="warning-check-heading">
                      <h5>{WARNING_CHECK_LABELS[name]}</h5>
                      <span className="status-label">
                        {STATUS_LABELS[check.status]}
                      </span>
                    </div>
                    <p>{check.explanation}</p>
                  </article>
                );
              })}
            </div>
          </section>
        );
      })}
      {warning.localized_text && (
        <details className="localized-warning-evidence">
          <summary>Inspect localized warning evidence</summary>
          <p>
            Analysis completed in {formatDuration(warning.analysis_duration_ms)}
            {warning.mean_ocr_confidence !== null
              ? ` · Mean OCR confidence ${Math.round(warning.mean_ocr_confidence * 100)}%`
              : ' · OCR confidence unavailable'}
          </p>
          {warning.bounding_box && (
            <p>
              OCR region: {warning.bounding_box.width} ×{' '}
              {warning.bounding_box.height} pixels in the preprocessed image
            </p>
          )}
          <pre className="raw-text">{warning.localized_text}</pre>
        </details>
      )}
    </section>
  );
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

function formatStatusCounts(
  counts: Record<VerificationStatus, number>,
): string {
  return (Object.keys(STATUS_LABELS) as VerificationStatus[])
    .filter((status) => counts[status] > 0)
    .map((status) => `${counts[status]} ${STATUS_COUNT_LABELS[status]}`)
    .join(' · ');
}
