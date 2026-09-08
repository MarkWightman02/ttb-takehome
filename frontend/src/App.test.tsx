import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

describe('application shell', () => {
  it('shows the OCR workflow while clearly deferring application comparison', () => {
    vi.stubEnv('DEV', false);
    render(<App />);

    expect(
      screen.getByRole('heading', { level: 1, name: 'TTB Label Verification' }),
    ).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Application data' }),
    ).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Upload label image' }),
    ).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Extracted label text' }),
    ).toBeVisible();
    expect(
      screen.getByText(/image upload and raw text extraction are available/i),
    ).toBeVisible();
    expect(screen.getByText('No label text has been extracted.')).toBeVisible();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Label image')).toHaveAttribute(
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
});
