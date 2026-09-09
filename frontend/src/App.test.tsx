import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

describe('application shell', () => {
  it('shows the four-step decision-support verification workflow', () => {
    vi.stubEnv('DEV', false);
    render(<App />);

    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'Verify label artwork against application data',
      }),
    ).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Application data' }),
    ).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Submitted label artwork' }),
    ).toBeVisible();
    expect(screen.getByRole('region', { name: 'Verify label' })).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Review results' }),
    ).toBeVisible();
    expect(screen.getByText(/values from the COLA application/i)).toBeVisible();
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
});
