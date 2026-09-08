import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LabelOcrWorkflow } from './LabelOcrWorkflow';

const labelFile = new File([new Uint8Array([1, 2, 3])], 'bourbon-label.png', {
  type: 'image/png',
});

const successfulPayload = {
  raw_text: 'OLD TOM DISTILLERY\n45% Alc./Vol.',
  engine: 'tesseract-cli',
  processing_duration_ms: 325,
  ocr_duration_ms: 280,
  warnings: ['The image is low resolution; extracted text may be incomplete.'],
  image: { width: 800, height: 400, format: 'PNG' as const },
};

describe('label OCR workflow', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:label-preview'),
      revokeObjectURL: vi.fn(),
    });
  });

  it('shows the selected filename and preview and allows a different image', () => {
    render(<LabelOcrWorkflow />);
    const input = screen.getByLabelText('Label image');

    fireEvent.change(input, { target: { files: [labelFile] } });
    expect(screen.getByText('bourbon-label.png')).toBeVisible();
    expect(
      screen.getByRole('img', { name: /bourbon-label.png/ }),
    ).toHaveAttribute('src', 'blob:label-preview');
    expect(
      screen.getByRole('button', { name: 'Extract label text' }),
    ).toBeEnabled();

    const replacement = new File([new Uint8Array([4])], 'replacement.webp', {
      type: 'image/webp',
    });
    fireEvent.change(input, { target: { files: [replacement] } });
    expect(screen.getByText('replacement.webp')).toBeVisible();
    expect(screen.queryByText('bourbon-label.png')).not.toBeInTheDocument();
  });

  it('uploads one image, announces loading, and displays raw OCR text', async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    const responsePromise = new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
    const fetchMock = vi.fn<
      (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    >(() => responsePromise);
    vi.stubGlobal('fetch', fetchMock);
    render(<LabelOcrWorkflow />);

    fireEvent.change(screen.getByLabelText('Label image'), {
      target: { files: [labelFile] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Extract label text' }));

    expect(
      screen.getByRole('button', { name: 'Extracting label text…' }),
    ).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Processing the selected image with local OCR.',
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const requestCall = fetchMock.mock.calls[0];
    expect(requestCall).toBeDefined();
    const url = requestCall?.[0];
    const request = requestCall?.[1];
    expect(url).toBe('/api/labels/ocr');
    expect(request?.method).toBe('POST');
    expect(request?.body).toBeInstanceOf(FormData);
    expect((request?.body as FormData).get('file')).toBe(labelFile);

    await act(async () => {
      resolveResponse?.({
        ok: true,
        json: async () => successfulPayload,
      } as Response);
      await responsePromise;
    });

    expect(await screen.findByText(/OLD TOM DISTILLERY/)).toBeVisible();
    expect(screen.getByText('Completed in 325 ms')).toBeVisible();
    expect(screen.getByText('Engine: tesseract-cli')).toBeVisible();
    expect(screen.getByText(successfulPayload.warnings[0]!)).toBeVisible();
    expect(
      screen.getByText(/has not been compared with application data/i),
    ).toBeVisible();
  });

  it('shows the typed API error and moves focus to it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({
          error: {
            code: 'invalid_image',
            message: 'The selected file is not a valid, readable image.',
          },
        }),
      }),
    );
    render(<LabelOcrWorkflow />);

    fireEvent.change(screen.getByLabelText('Label image'), {
      target: { files: [labelFile] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Extract label text' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'The selected file is not a valid, readable image.',
    );
    expect(alert).toHaveFocus();
    expect(screen.queryByText(/OLD TOM DISTILLERY/)).not.toBeInTheDocument();
  });

  it('supports drag and drop while still providing a file picker', () => {
    render(<LabelOcrWorkflow />);

    fireEvent.drop(screen.getByTestId('upload-drop-zone'), {
      dataTransfer: { files: [labelFile] },
    });

    expect(screen.getByText('bourbon-label.png')).toBeVisible();
    expect(screen.getByLabelText('Label image')).toHaveAttribute(
      'type',
      'file',
    );
  });
});
