import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

describe('application shell', () => {
  it('shows the four-step decision-support verification workflow', () => {
    vi.stubEnv('DEV', false);
    render(<App />);

    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'Label Verification',
      }),
    ).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Application information' }),
    ).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Submitted label' }),
    ).toBeVisible();
    expect(screen.getByRole('region', { name: 'Verify label' })).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Review results' }),
    ).toBeVisible();
    expect(
      screen.getByText(/Enter the application information, upload the/i),
    ).toBeVisible();
    expect(screen.getByText(/do not approve, reject/i)).toBeVisible();
    expect(
      screen.getByText('No verification has been performed.'),
    ).toBeVisible();
    expect(screen.getAllByRole('textbox')).toHaveLength(5);
    expect(screen.getByRole('spinbutton')).toBeVisible();
    expect(screen.getByLabelText('Choose label image')).toHaveAttribute(
      'accept',
      'image/png,image/jpeg,image/webp',
    );
    expect(
      screen.getByRole('link', { name: 'Skip to main content' }),
    ).toHaveAttribute('href', '#main-content');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
  });

  it('checks backend availability in development', async () => {
    vi.stubEnv('DEV', true);
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    expect(await screen.findByText('Backend available')).toBeVisible();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('omits the health indicator and request from the production shell', () => {
    vi.stubEnv('DEV', false);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    expect(
      screen.queryByLabelText('Development connection status'),
    ).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('keeps single-label review as the default and exposes optional batch verification', () => {
    vi.stubEnv('DEV', false);
    render(<App />);

    expect(
      screen.getByRole('button', { name: 'Single label' }),
    ).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Batch verification' }));

    expect(
      screen.getByRole('button', { name: 'Batch verification' }),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(
      screen.getByRole('region', { name: 'Upload application CSV' }),
    ).toBeVisible();
    expect(
      screen.queryByRole('region', { name: 'Application information' }),
    ).not.toBeInTheDocument();
  });
});
