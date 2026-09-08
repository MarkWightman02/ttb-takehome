import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent, DragEvent, FormEvent } from 'react';

type WorkflowState = 'idle' | 'loading' | 'success' | 'error';

interface OcrResponse {
  raw_text: string;
  engine: string;
  processing_duration_ms: number;
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

class OcrRequestError extends Error {}

const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export function LabelOcrWorkflow() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [state, setState] = useState<WorkflowState>('idle');
  const [result, setResult] = useState<OcrResponse | null>(null);
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
      setError('Choose one label image before extracting text.');
      setState('error');
      return;
    }

    setError(null);
    setResult(null);
    setState('loading');
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await fetch('/api/labels/ocr', {
        method: 'POST',
        body: formData,
      });
      const payload: unknown = await readJson(response);
      if (!response.ok) {
        const apiError = payload as ApiErrorResponse;
        throw new OcrRequestError(
          apiError.error?.message ??
            'The label could not be processed. Try another image.',
        );
      }
      if (!isOcrResponse(payload)) {
        throw new OcrRequestError(
          'The server returned an unexpected OCR response.',
        );
      }

      setResult(payload);
      setState('success');
    } catch (requestError) {
      setError(
        requestError instanceof OcrRequestError
          ? requestError.message
          : 'The OCR service could not be reached. Check the connection and try again.',
      );
      setState('error');
    }
  }

  return (
    <>
      <li>
        <section className="step-card" aria-labelledby="upload-title">
          <div className="step-heading">
            <span className="step-number" aria-hidden="true">
              2
            </span>
            <h2 id="upload-title">Upload label image</h2>
          </div>
          <p>
            Choose one PNG, JPEG, or WebP image. The image is processed for this
            request and is not retained by the application.
          </p>

          <form onSubmit={handleSubmit} aria-describedby="upload-guidance">
            <div
              className="upload-area"
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleDrop}
              data-testid="upload-drop-zone"
            >
              <label className="file-label" htmlFor="label-image">
                Label image
              </label>
              <input
                id="label-image"
                className="file-picker"
                type="file"
                accept={ACCEPTED_TYPES.join(',')}
                onChange={handleFileChange}
                disabled={state === 'loading'}
                aria-invalid={state === 'error'}
                aria-describedby={
                  state === 'error'
                    ? 'upload-guidance upload-error'
                    : 'upload-guidance'
                }
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

            {error && (
              <div
                id="upload-error"
                className="workflow-error"
                role="alert"
                tabIndex={-1}
                ref={errorRef}
              >
                <strong>Text extraction failed</strong>
                <p>{error}</p>
              </div>
            )}

            <button
              className="primary-button"
              type="submit"
              disabled={!selectedFile || state === 'loading'}
            >
              {state === 'loading'
                ? 'Extracting label text…'
                : 'Extract label text'}
            </button>
            {state === 'loading' && (
              <p className="loading-status" role="status" aria-live="polite">
                Processing the selected image with local OCR.
              </p>
            )}
          </form>
        </section>
      </li>

      <li className="results-step">
        <section className="step-card" aria-labelledby="results-title">
          <div className="step-heading">
            <span className="step-number" aria-hidden="true">
              3
            </span>
            <h2 id="results-title">Extracted label text</h2>
          </div>
          <p>
            This is raw OCR output from the label image. It has not been
            compared with application data or checked for compliance.
          </p>

          {result ? (
            <div className="ocr-result" tabIndex={-1} ref={resultRef}>
              <div
                className="result-summary"
                aria-label="OCR processing details"
              >
                <span>
                  Completed in {formatDuration(result.processing_duration_ms)}
                </span>
                <span>Engine: {result.engine}</span>
                <span>
                  Image: {result.image.width} × {result.image.height}{' '}
                  {result.image.format}
                </span>
              </div>
              {result.warnings.length > 0 && (
                <div className="ocr-warning">
                  <strong>Review the extracted text</strong>
                  <ul>
                    {result.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
              <h3>Raw OCR text</h3>
              <pre className="raw-text">
                {result.raw_text || 'No text was detected in this image.'}
              </pre>
            </div>
          ) : (
            <div className="placeholder results-placeholder">
              <p>No label text has been extracted.</p>
              <p>Choose an image above, then select “Extract label text.”</p>
            </div>
          )}
        </section>
      </li>
    </>
  );
}

function isOcrResponse(payload: unknown): payload is OcrResponse {
  if (typeof payload !== 'object' || payload === null) return false;
  const candidate = payload as Partial<OcrResponse>;
  return (
    typeof candidate.raw_text === 'string' &&
    typeof candidate.engine === 'string' &&
    typeof candidate.processing_duration_ms === 'number' &&
    typeof candidate.ocr_duration_ms === 'number' &&
    Array.isArray(candidate.warnings) &&
    candidate.warnings.every((warning) => typeof warning === 'string') &&
    typeof candidate.image === 'object' &&
    candidate.image !== null &&
    typeof candidate.image.width === 'number' &&
    typeof candidate.image.height === 'number' &&
    ['PNG', 'JPEG', 'WEBP'].includes(candidate.image.format)
  );
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
