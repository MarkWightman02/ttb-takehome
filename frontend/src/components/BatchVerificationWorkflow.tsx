import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import {
  ACCEPTED_IMAGE_TYPES,
  BATCH_CONCURRENCY,
  BATCH_TEMPLATE_CSV,
  MAX_BATCH_SIZE,
  batchIssueSummary,
  batchResultsCsv,
  deriveBatchItemStatus,
  mapBatchFiles,
  parseBatchCsv,
  runBoundedQueue,
} from '../batchVerification';
import type {
  BatchItemStatus,
  BatchManifestRecord,
  MappedBatchItem,
} from '../batchVerification';
import { VerificationRequestError, verifyLabel } from '../verification';
import type { VerificationResponse } from '../verification';
import { VerificationResults } from './LabelOcrWorkflow';

type BatchPhase = 'setup' | 'running' | 'complete' | 'cancelled';

const BATCH_STATUS_LABELS: Record<BatchItemStatus, string> = {
  invalid: 'Invalid',
  ready: 'Ready',
  queued: 'Queued',
  processing: 'Processing',
  match: 'Automated checks matched',
  review: 'Needs review',
  mismatch: 'Contains mismatch',
  processing_error: 'Processing failed',
  cancelled: 'Not processed',
};

export function BatchVerificationWorkflow() {
  const [manifestName, setManifestName] = useState<string | null>(null);
  const [records, setRecords] = useState<BatchManifestRecord[]>([]);
  const [manifestErrors, setManifestErrors] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [items, setItems] = useState<MappedBatchItem[]>([]);
  const [unmatchedFiles, setUnmatchedFiles] = useState<string[]>([]);
  const [mappingErrors, setMappingErrors] = useState<string[]>([]);
  const [phase, setPhase] = useState<BatchPhase>('setup');
  const [batchNotice, setBatchNotice] = useState<string | null>(null);
  const cancelRequested = useRef(false);
  const imageInputRef = useRef<HTMLInputElement>(null);

  useEffect(
    () => () => {
      cancelRequested.current = true;
    },
    [],
  );

  function remap(nextRecords: BatchManifestRecord[], nextFiles: File[]) {
    const mapping = mapBatchFiles(nextRecords, nextFiles);
    setItems(mapping.items);
    setUnmatchedFiles(mapping.unmatchedFiles);
    setMappingErrors(mapping.errors);
    setPhase('setup');
    setBatchNotice(null);
    cancelRequested.current = false;
  }

  async function handleManifestChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      setManifestName(null);
      setRecords([]);
      setManifestErrors([]);
      remap([], files);
      return;
    }
    setManifestName(file.name);
    try {
      const parsed = parseBatchCsv(await file.text());
      setRecords(parsed.records);
      setManifestErrors(parsed.errors);
      remap(parsed.records, files);
    } catch {
      setRecords([]);
      setManifestErrors(['The selected CSV could not be read.']);
      remap([], files);
    }
  }

  function handleImagesChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files ?? []);
    setFiles(selected);
    remap(records, selected);
  }

  async function processItems(eligibleIds: Set<string>) {
    const pending = items.filter(
      (item) =>
        eligibleIds.has(item.id) && item.file && item.errors.length === 0,
    );
    if (!pending.length) {
      setBatchNotice('No valid mapped items are ready to process.');
      return;
    }
    cancelRequested.current = false;
    setBatchNotice(null);
    setPhase('running');
    setItems((current) =>
      current.map((item) =>
        eligibleIds.has(item.id)
          ? { ...item, status: 'queued', processingError: null }
          : item,
      ),
    );

    const outcomes = await runBoundedQueue(
      pending,
      async (item) => verifyLabel(item.application, item.file!),
      {
        concurrency: BATCH_CONCURRENCY,
        shouldStop: () => cancelRequested.current,
        onStart: (item) => {
          setItems((current) =>
            updateItem(current, item.id, { status: 'processing' }),
          );
        },
        onSettled: (outcome, item) => {
          if (outcome.status === 'fulfilled') {
            const result = outcome.value as VerificationResponse;
            setItems((current) =>
              updateItem(current, item.id, {
                status: deriveBatchItemStatus(result),
                result,
                processingError: null,
                file: null,
              }),
            );
          } else {
            const error = requestErrorMessage(outcome.reason);
            setItems((current) =>
              updateItem(current, item.id, {
                status: 'processing_error',
                processingError: error,
              }),
            );
          }
        },
      },
    );

    const skipped = new Set(
      outcomes
        .map((outcome, index) =>
          outcome.status === 'skipped' ? pending[index]!.id : null,
        )
        .filter((id): id is string => id !== null),
    );
    setItems((current) =>
      current.map((item) =>
        skipped.has(item.id) ? { ...item, status: 'cancelled' } : item,
      ),
    );
    setFiles([]);
    if (imageInputRef.current) imageInputRef.current.value = '';
    setPhase(cancelRequested.current ? 'cancelled' : 'complete');
  }

  function runBatch() {
    void processItems(
      new Set(
        items
          .filter(
            (item) => item.status === 'ready' || item.status === 'cancelled',
          )
          .map((item) => item.id),
      ),
    );
  }

  function retryFailures() {
    void processItems(
      new Set(
        items
          .filter((item) => item.status === 'processing_error' && item.file)
          .map((item) => item.id),
      ),
    );
  }

  function stopScheduling() {
    cancelRequested.current = true;
    setBatchNotice('Stopping after the currently processing labels finish.');
  }

  function downloadTemplate() {
    downloadCsv(BATCH_TEMPLATE_CSV, 'ttb-batch-template.csv');
  }

  function exportResults() {
    downloadCsv(batchResultsCsv(items), 'ttb-batch-results.csv');
  }

  const counts = countStatuses(items);
  const completed =
    counts.match +
    counts.review +
    counts.mismatch +
    counts.processing_error +
    counts.invalid;
  const currentlyProcessing = items.filter(
    (item) => item.status === 'processing',
  );
  const canRun =
    phase !== 'running' &&
    mappingErrors.length === 0 &&
    items.some(
      (item) => item.status === 'ready' || item.status === 'cancelled',
    );
  const canRetry =
    phase !== 'running' &&
    items.some((item) => item.status === 'processing_error' && item.file);
  const hasResults = items.some((item) => item.result || item.processingError);

  return (
    <div className="batch-workflow">
      <ol className="batch-steps" aria-label="Batch verification workflow">
        <li>
          <section className="step-card" aria-labelledby="batch-manifest-title">
            <BatchStepHeading number="1" id="batch-manifest-title">
              Upload application CSV
            </BatchStepHeading>
            <p>
              Add one row per application. Filenames connect each row to its
              label image.
            </p>
            <button
              className="secondary-button"
              type="button"
              onClick={downloadTemplate}
            >
              Download CSV template
            </button>
            <label
              className="file-label batch-file-label"
              htmlFor="batch-manifest"
            >
              Choose application CSV
            </label>
            <input
              id="batch-manifest"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => void handleManifestChange(event)}
              disabled={phase === 'running'}
            />
            {manifestName && (
              <p className="input-summary">Selected: {manifestName}</p>
            )}
            <MessageList title="CSV problems" messages={manifestErrors} />
          </section>
        </li>

        <li>
          <section className="step-card" aria-labelledby="batch-images-title">
            <BatchStepHeading number="2" id="batch-images-title">
              Select label images
            </BatchStepHeading>
            <p>
              Choose up to {MAX_BATCH_SIZE} PNG, JPEG, or WebP images. Files
              remain in your browser until their individual request runs.
            </p>
            <label className="file-label" htmlFor="batch-images">
              Choose label images
            </label>
            <input
              id="batch-images"
              ref={imageInputRef}
              type="file"
              multiple
              accept={ACCEPTED_IMAGE_TYPES.join(',')}
              onChange={handleImagesChange}
              disabled={phase === 'running'}
            />
            <p className="input-summary">
              {phase === 'setup'
                ? files.length
                : items.filter((item) => item.file !== null).length}{' '}
              image files retained for pending or failed items
            </p>
            <MessageList
              title="Image selection problems"
              messages={mappingErrors}
            />
            <MessageList
              title="Images not represented in the CSV"
              messages={unmatchedFiles}
            />
          </section>
        </li>

        <li className="batch-wide-step">
          <section className="step-card" aria-labelledby="batch-mapping-title">
            <BatchStepHeading number="3" id="batch-mapping-title">
              Review mapping and validation
            </BatchStepHeading>
            <p>
              Filename matching ignores case, Unicode composition, surrounding
              whitespace, and CSV path prefixes. Ambiguous or missing matches
              are never guessed.
            </p>
            {items.length ? (
              <BatchTable items={items} showDetails={false} />
            ) : (
              <div className="placeholder">
                Upload a CSV and select images to review mapping.
              </div>
            )}
          </section>
        </li>

        <li className="batch-wide-step">
          <section className="step-card" aria-labelledby="batch-run-title">
            <BatchStepHeading number="4" id="batch-run-title">
              Run batch verification
            </BatchStepHeading>
            <p>
              Two labels are verified at a time through the same endpoint used
              for single-label review. Invalid rows remain visible and do not
              stop valid items.
            </p>
            {items.length > 0 && (
              <div className="batch-progress" role="status" aria-live="polite">
                <progress value={completed} max={items.length}>
                  {completed} of {items.length}
                </progress>
                <p>
                  Total {items.length} · Completed {completed} · Remaining{' '}
                  {Math.max(
                    0,
                    items.length - completed - currentlyProcessing.length,
                  )}{' '}
                  · Processing {currentlyProcessing.length} · Successful{' '}
                  {counts.match + counts.review + counts.mismatch} · Failed{' '}
                  {counts.processing_error + counts.invalid}
                </p>
                {currentlyProcessing.length > 0 && (
                  <p>
                    Currently processing:{' '}
                    {currentlyProcessing
                      .map((item) => item.imageFilename)
                      .join(', ')}
                  </p>
                )}
              </div>
            )}
            {batchNotice && <p className="batch-notice">{batchNotice}</p>}
            <div className="batch-actions">
              <button
                className="primary-button"
                type="button"
                disabled={!canRun}
                onClick={runBatch}
              >
                {phase === 'running' ? 'Verifying batch…' : 'Verify Batch'}
              </button>
              {phase === 'running' && (
                <button
                  className="secondary-button"
                  type="button"
                  onClick={stopScheduling}
                >
                  Stop after current labels
                </button>
              )}
              {canRetry && (
                <button
                  className="secondary-button"
                  type="button"
                  onClick={retryFailures}
                >
                  Retry failed items
                </button>
              )}
            </div>
          </section>
        </li>

        <li className="batch-wide-step">
          <section className="step-card" aria-labelledby="batch-results-title">
            <BatchStepHeading number="5" id="batch-results-title">
              Review and export results
            </BatchStepHeading>
            <p>
              A mismatch takes precedence over review or missing evidence.
              Processing failures remain separate from label results.
            </p>
            {hasResults ? (
              <>
                <BatchSummary items={items} />
                <button
                  className="secondary-button"
                  type="button"
                  onClick={exportResults}
                >
                  Export results CSV
                </button>
                <BatchTable items={items} showDetails />
              </>
            ) : (
              <div className="placeholder">
                No batch verification has been performed.
              </div>
            )}
          </section>
        </li>
      </ol>
    </div>
  );
}

function BatchStepHeading({
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

function MessageList({
  title,
  messages,
}: {
  title: string;
  messages: string[];
}) {
  if (!messages.length) return null;
  return (
    <div className="workflow-error batch-validation" role="alert">
      <strong>{title}</strong>
      <ul>
        {messages.map((message, index) => (
          <li key={`${message}-${index}`}>{message}</li>
        ))}
      </ul>
    </div>
  );
}

function BatchTable({
  items,
  showDetails,
}: {
  items: MappedBatchItem[];
  showDetails: boolean;
}) {
  return (
    <div className="batch-table-wrap">
      <table className="batch-table">
        <caption className="visually-hidden">
          {showDetails
            ? 'Batch verification results'
            : 'CSV and image filename mapping'}
        </caption>
        <thead>
          <tr>
            <th scope="col">CSV row</th>
            <th scope="col">Image</th>
            <th scope="col">Brand</th>
            <th scope="col">Status</th>
            <th scope="col">Details</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.rowNumber}</td>
              <td>{item.imageFilename || 'Missing filename'}</td>
              <td>{item.application.brand_name || 'Missing brand'}</td>
              <td>
                <span className={`batch-status batch-status-${item.status}`}>
                  {BATCH_STATUS_LABELS[item.status]}
                </span>
              </td>
              <td>
                {item.errors.length > 0 && <span>{item.errors.join(' ')}</span>}
                {item.processingError && <span>{item.processingError}</span>}
                {item.result && !showDetails && (
                  <span>{batchIssueSummary(item.result)}</span>
                )}
                {item.result && showDetails && (
                  <BatchResultDetails item={item} result={item.result} />
                )}
                {!item.errors.length &&
                  !item.processingError &&
                  !item.result && (
                    <span>
                      {item.file ? 'Image mapped.' : 'Waiting for processing.'}
                    </span>
                  )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BatchResultDetails({
  item,
  result,
}: {
  item: MappedBatchItem;
  result: VerificationResponse;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <p className="batch-issue-summary">{batchIssueSummary(result)}</p>
      <details
        className="batch-result-details"
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary>
          Inspect detailed result ·{' '}
          {formatDuration(result.total_verification_duration_ms)}
        </summary>
        {open && (
          <VerificationResults result={result} idPrefix={`${item.id}-`} />
        )}
      </details>
    </>
  );
}

function BatchSummary({ items }: { items: MappedBatchItem[] }) {
  const counts = countStatuses(items);
  const missingEvidence = items.filter(
    (item) =>
      item.result &&
      Object.values(item.result.results).some(
        (result) => result.status === 'not_found',
      ),
  ).length;
  return (
    <div className="batch-summary" role="status" aria-live="polite">
      <strong>Batch summary</strong>
      <dl>
        <div>
          <dt>Total</dt>
          <dd>{items.length}</dd>
        </div>
        <div>
          <dt>Automated checks matched</dt>
          <dd>{counts.match}</dd>
        </div>
        <div>
          <dt>Needs review</dt>
          <dd>{counts.review}</dd>
        </div>
        <div>
          <dt>Contains mismatch</dt>
          <dd>{counts.mismatch}</dd>
        </div>
        <div>
          <dt>Missing evidence</dt>
          <dd>{missingEvidence}</dd>
        </div>
        <div>
          <dt>Processing failed</dt>
          <dd>{counts.processing_error}</dd>
        </div>
        <div>
          <dt>Invalid input</dt>
          <dd>{counts.invalid}</dd>
        </div>
      </dl>
    </div>
  );
}

function countStatuses(
  items: MappedBatchItem[],
): Record<BatchItemStatus, number> {
  const counts = Object.fromEntries(
    Object.keys(BATCH_STATUS_LABELS).map((status) => [status, 0]),
  ) as Record<BatchItemStatus, number>;
  for (const item of items) counts[item.status] += 1;
  return counts;
}

function updateItem(
  items: MappedBatchItem[],
  id: string,
  update: Partial<MappedBatchItem>,
): MappedBatchItem[] {
  return items.map((item) => (item.id === id ? { ...item, ...update } : item));
}

function requestErrorMessage(error: unknown): string {
  return error instanceof VerificationRequestError
    ? error.message
    : 'The verification service could not be reached. Check the connection and try again.';
}

function downloadCsv(contents: string, filename: string) {
  const url = URL.createObjectURL(
    new Blob([contents], { type: 'text/csv;charset=utf-8' }),
  );
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function formatDuration(durationMs: number): string {
  return durationMs < 1_000
    ? `${Math.round(durationMs)} ms`
    : `${(durationMs / 1_000).toFixed(1)} s`;
}
