import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BackendHealth } from './BackendHealth';

describe('backend connection status', () => {
  it('announces backend availability after a valid health response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: 'ok',
          service: 'ttb-label-verification',
        }),
      }),
    );
    render(<BackendHealth />);

    expect(screen.getByRole('status')).toHaveTextContent(
      'Checking backend connection',
    );
    expect(await screen.findByText('Backend available')).toHaveAttribute(
      'role',
      'status',
    );
    expect(
      screen.getByRole('button', { name: 'Check connection' }),
    ).toBeEnabled();
  });

  it.each([
    { ok: false, json: async () => ({ status: 'ok' }) },
    { ok: true, json: async () => ({ status: 'unhealthy' }) },
    { ok: true, json: async () => null },
    {
      ok: true,
      json: async () => {
        throw new SyntaxError('Invalid JSON');
      },
    },
  ])(
    'does not report an invalid health response as available (%#)',
    async (response) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
      render(<BackendHealth />);

      expect(await screen.findByText(/Backend unavailable/)).toBeVisible();
      expect(screen.queryByText('Backend available')).not.toBeInTheDocument();
    },
  );

  it('allows a failed connection to be checked again', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Network error'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'ok' }),
      });
    vi.stubGlobal('fetch', fetchMock);
    render(<BackendHealth />);

    await screen.findByText(/Backend unavailable/);
    fireEvent.click(screen.getByRole('button', { name: 'Check connection' }));
    expect(await screen.findByText('Backend available')).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('ends a stalled health check after five seconds', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal('fetch', fetchMock);
    render(<BackendHealth />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(screen.getByRole('status')).toHaveTextContent('Backend unavailable');
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.signal?.aborted).toBe(true);
  });

  it('aborts an in-flight request when the component unmounts', () => {
    const fetchMock = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal('fetch', fetchMock);
    const { unmount } = render(<BackendHealth />);

    unmount();
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.signal?.aborted).toBe(true);
  });
});
