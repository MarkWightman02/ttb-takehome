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

type Status = 'match' | 'review' | 'mismatch' | 'not_found';

function fieldResult(
  field: 'brand_name' | 'class_type' | 'abv' | 'net_contents',
  status: Status,
  expected: string,
  detected: string | null,
) {
  return {
    field,
    expected_raw: expected,
    extracted_raw: detected,
    expected_normalized: expected.toLowerCase(),
    extracted_normalized: detected?.toLowerCase() ?? null,
    status,
    explanation:
      status === 'match'
        ? 'Matches after capitalization and punctuation normalization.'
        : status === 'not_found'
          ? `No reliable ${field} value was found in the extracted label text.`
          : status === 'review'
            ? 'Possible match found, but OCR differences require manual review.'
            : 'The detected value differs from the application value.',
    evidence: detected ? [detected] : [],
    similarity_score: status === 'review' ? 0.88 : null,
  };
}

const successfulPayload = {
  expected: {
    brand_name: 'Old Tom Distillery',
    class_type: 'Kentucky Straight Bourbon Whiskey',
    abv: 45,
    net_contents: '750 mL',
  },
  candidates: { brand_name: [], class_type: [], abv: [], net_contents: [] },
  results: {
    brand_name: fieldResult(
      'brand_name',
      'match',
      'Old Tom Distillery',
      'OLD TOM DISTILLERY',
    ),
    class_type: fieldResult(
      'class_type',
      'match',
      'Kentucky Straight Bourbon Whiskey',
      'Kentucky Straight Bourbon Whiskey',
    ),
    abv: fieldResult('abv', 'match', '45%', '45% Alc./Vol.'),
    net_contents: fieldResult('net_contents', 'match', '750 mL', '750 mL'),
  },
  overall_summary: 'All checked application fields match the label.',
  raw_text:
    'OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n45% Alc./Vol.\n750 mL',
  engine: 'tesseract-cli',
  total_verification_duration_ms: 325,
  ocr_duration_ms: 280,
  warnings: ['The image is low resolution; extracted text may be incomplete.'],
  image: { width: 800, height: 400, format: 'PNG' as const },
};

describe('label verification workflow', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:label-preview'),
      revokeObjectURL: vi.fn(),
    });
  });

  it('accepts natural application values and previews one selected image', () => {
    render(<LabelOcrWorkflow />);
    enterApplicationValues();
    fireEvent.change(screen.getByLabelText('Choose label image'), {
      target: { files: [labelFile] },
    });

    expect(screen.getByLabelText('Brand name')).toHaveValue(
      'Old Tom Distillery',
    );
    expect(screen.getByLabelText('Class/type designation')).toHaveValue(
      'Kentucky Straight Bourbon Whiskey',
    );
    expect(screen.getByLabelText('Alcohol content / ABV (%)')).toHaveValue(45);
    expect(screen.getByLabelText('Net contents')).toHaveValue('750 mL');
    expect(screen.getByText('bourbon-label.png')).toBeVisible();
    expect(
      screen.getByRole('img', { name: /bourbon-label.png/ }),
    ).toHaveAttribute('src', 'blob:label-preview');
  });

  it('submits one verification request, announces loading, and shows all matches', async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    const responsePromise = new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
    const fetchMock = vi.fn<
      (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    >(() => responsePromise);
    vi.stubGlobal('fetch', fetchMock);
    render(<LabelOcrWorkflow />);
    completeForm();

    fireEvent.click(screen.getByRole('button', { name: 'Verify Label' }));

    expect(
      screen.getByRole('button', { name: 'Verifying label…' }),
    ).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Running local OCR and comparing application fields.',
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const [url, request] = fetchMock.mock.calls[0]!;
    expect(url).toBe('/api/labels/verify');
    expect(request?.method).toBe('POST');
    const body = request?.body as FormData;
    expect(body.get('brand_name')).toBe('Old Tom Distillery');
    expect(body.get('class_type')).toBe('Kentucky Straight Bourbon Whiskey');
    expect(body.get('abv')).toBe('45');
    expect(body.get('net_contents')).toBe('750 mL');
    expect(body.get('file')).toBe(labelFile);

    await act(async () => {
      resolveResponse?.({
        ok: true,
        json: async () => successfulPayload,
      } as Response);
      await responsePromise;
    });

    expect(
      await screen.findByText(
        'All checked application fields match the label.',
      ),
    ).toBeVisible();
    expect(screen.getAllByText('Match')).toHaveLength(4);
    expect(screen.getAllByText('Brand name')).toHaveLength(2);
    expect(screen.getByText('Alcohol content / ABV')).toBeVisible();
    expect(screen.getByText('Inspect raw OCR evidence')).toBeVisible();
    fireEvent.click(screen.getByText('Inspect raw OCR evidence'));
    expect(screen.getAllByText(/OLD TOM DISTILLERY/).length).toBeGreaterThan(0);
    expect(screen.getByText('Engine: tesseract-cli')).toBeVisible();
    expect(screen.getByText(successfulPayload.warnings[0]!)).toBeVisible();
  });

  it('communicates mixed mismatch, review, and not-found statuses in text', async () => {
    const mixedPayload = {
      ...successfulPayload,
      overall_summary: 'One or more application fields do not match the label.',
      results: {
        ...successfulPayload.results,
        brand_name: fieldResult(
          'brand_name',
          'review',
          'Old Tom Distillery',
          'OLD T0M DISTILLERY',
        ),
        class_type: fieldResult(
          'class_type',
          'mismatch',
          'Bourbon Whiskey',
          'Vodka',
        ),
        abv: fieldResult('abv', 'not_found', '45%', null),
      },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => mixedPayload }),
    );
    render(<LabelOcrWorkflow />);
    completeForm();
    fireEvent.click(screen.getByRole('button', { name: 'Verify Label' }));

    expect(
      await screen.findByText(
        'One or more application fields do not match the label.',
      ),
    ).toBeVisible();
    expect(screen.getByText('Review')).toBeVisible();
    expect(screen.getByText('Mismatch')).toBeVisible();
    expect(screen.getByText('Not found')).toBeVisible();
    expect(screen.getByText('Not detected')).toBeVisible();
    expect(screen.getAllByText(/manual review/i).length).toBeGreaterThan(0);
  });

  it('shows a typed API error and moves focus to it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({
          error: {
            message: 'The selected file is not a valid, readable image.',
          },
        }),
      }),
    );
    render(<LabelOcrWorkflow />);
    completeForm();
    fireEvent.click(screen.getByRole('button', { name: 'Verify Label' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'The selected file is not a valid, readable image.',
    );
    expect(alert).toHaveFocus();
  });

  it('requires a file and supports drag and drop', () => {
    render(<LabelOcrWorkflow />);
    enterApplicationValues();
    fireEvent.submit(
      screen.getByRole('button', { name: 'Verify Label' }).closest('form')!,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Choose one label image before verifying the label.',
    );

    fireEvent.drop(screen.getByTestId('upload-drop-zone'), {
      dataTransfer: { files: [labelFile] },
    });
    expect(screen.getByText('bourbon-label.png')).toBeVisible();
  });
});

function enterApplicationValues() {
  fireEvent.change(screen.getByLabelText('Brand name'), {
    target: { value: 'Old Tom Distillery' },
  });
  fireEvent.change(screen.getByLabelText('Class/type designation'), {
    target: { value: 'Kentucky Straight Bourbon Whiskey' },
  });
  fireEvent.change(screen.getByLabelText('Alcohol content / ABV (%)'), {
    target: { value: '45' },
  });
  fireEvent.change(screen.getByLabelText('Net contents'), {
    target: { value: '750 mL' },
  });
}

function completeForm() {
  enterApplicationValues();
  fireEvent.change(screen.getByLabelText('Choose label image'), {
    target: { files: [labelFile] },
  });
}
