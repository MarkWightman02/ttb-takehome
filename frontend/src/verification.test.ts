import { describe, expect, it, vi } from 'vitest';
import {
  VERIFICATION_REQUEST_TIMEOUT_MS,
  buildVerificationFormData,
  verifyLabel,
} from './verification';

const application = {
  brand_name: "Stone's Throw",
  class_type: 'Kentucky Straight Bourbon Whiskey',
  abv: '45',
  net_contents: '750 mL',
  producer_name: 'Example Distillery LLC',
  producer_address: 'Louisville, KY',
  imported_product: true,
  country_origin: 'Canada',
};

describe('shared single-label verification request', () => {
  it('builds equivalent multipart input for the single and batch workflows', () => {
    const file = new File(['image'], 'label.png', { type: 'image/png' });

    const singleRequest = buildVerificationFormData(application, file);
    const batchRequest = buildVerificationFormData(application, file);

    expect([...batchRequest.entries()]).toEqual([...singleRequest.entries()]);
    expect(batchRequest.get('file')).toBe(file);
    expect(batchRequest.get('country_origin')).toBe('Canada');
  });

  it('turns a stalled request into an isolated, retryable timeout error', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            );
          }),
      ),
    );
    const file = new File(['image'], 'label.png', { type: 'image/png' });
    const timedOut = expect(verifyLabel(application, file)).rejects.toThrow(
      'Verification timed out',
    );

    await vi.advanceTimersByTimeAsync(VERIFICATION_REQUEST_TIMEOUT_MS);
    await timedOut;
  });
});
