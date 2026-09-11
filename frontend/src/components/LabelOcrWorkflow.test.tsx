import {
  act,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LabelOcrWorkflow } from './LabelOcrWorkflow';

const labelFile = new File([new Uint8Array([1, 2, 3])], 'bourbon-label.png', {
  type: 'image/png',
});

type Status = 'match' | 'review' | 'mismatch' | 'not_found' | 'not_applicable';

function warningCheck(status: Status, explanation: string) {
  return { status, explanation, evidence: [], measurements: {} };
}

const warningChecks = {
  presence: warningCheck('match', 'A likely Government Warning was located.'),
  wording: warningCheck(
    'match',
    'The extracted warning matches the prescribed wording.',
  ),
  heading_capitalization: warningCheck(
    'match',
    'OCR preserves the heading as uppercase “GOVERNMENT WARNING.”',
  ),
  heading_boldness: warningCheck(
    'review',
    'Font weight requires manual confirmation because visual evidence is borderline.',
  ),
  body_not_bold: warningCheck(
    'review',
    'Body font weight requires manual confirmation.',
  ),
  continuous_statement: warningCheck(
    'match',
    'Both numbered portions occur in sequence within one OCR block.',
  ),
  separation: warningCheck(
    'review',
    'Separate-and-apart presentation requires manual review.',
  ),
  legibility_contrast: warningCheck(
    'review',
    'Contrast requires reviewer confirmation.',
  ),
  type_size: warningCheck(
    'review',
    'A minimum type size of 2 mm applies, but pixels do not establish physical size.',
  ),
  characters_per_inch: warningCheck(
    'review',
    'The applicable limit is 25 characters per inch; physical scale is unavailable.',
  ),
};

function fieldResult(
  field:
    | 'brand_name'
    | 'class_type'
    | 'abv'
    | 'net_contents'
    | 'producer_name'
    | 'producer_address'
    | 'country_origin',
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
        : status === 'not_applicable'
          ? 'Country of origin is not checked for a domestic product.'
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
    producer_name: 'Old Tom Distillery LLC',
    producer_address: 'Louisville, Kentucky',
    imported_product: false,
    country_origin: null,
  },
  candidates: {
    brand_name: [],
    class_type: [],
    abv: [],
    net_contents: [],
    producer_name: [],
    producer_address: [],
    country_origin: [],
  },
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
    producer_name: fieldResult(
      'producer_name',
      'match',
      'Old Tom Distillery LLC',
      'OLD TOM DISTILLERY LLC',
    ),
    producer_address: fieldResult(
      'producer_address',
      'match',
      'Louisville, Kentucky',
      'LOUISVILLE, KY',
    ),
    country_origin: fieldResult(
      'country_origin',
      'not_applicable',
      'Not applicable',
      null,
    ),
  },
  government_warning: {
    overall_status: 'review' as const,
    localized_text:
      'GOVERNMENT WARNING: (1) According to the Surgeon General ... (2) Consumption ...',
    source_lines: [
      'GOVERNMENT WARNING: (1) According to the Surgeon General ...',
    ],
    bounding_box: {
      left: 40,
      top: 220,
      width: 710,
      height: 130,
      coordinate_space: 'preprocessed_image' as const,
    },
    mean_ocr_confidence: 0.92,
    analysis_duration_ms: 12,
    checks: warningChecks,
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
    expect(screen.getByLabelText('Producer / bottler name')).toHaveValue(
      'Old Tom Distillery LLC',
    );
    expect(screen.getByLabelText('Producer / bottler address')).toHaveValue(
      'Louisville, KY',
    );
    expect(screen.getByLabelText('No')).toBeChecked();
    expect(
      screen.queryByLabelText('Country of origin'),
    ).not.toBeInTheDocument();
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
    expect(body.get('producer_name')).toBe('Old Tom Distillery LLC');
    expect(body.get('producer_address')).toBe('Louisville, KY');
    expect(body.get('imported_product')).toBe('false');
    expect(body.get('country_origin')).toBeNull();
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
    expect(
      within(screen.getByLabelText('Application field results')).getAllByText(
        'Match',
      ),
    ).toHaveLength(6);
    expect(
      within(screen.getByLabelText('Application field results')).getAllByText(
        'Not applicable',
      ),
    ).toHaveLength(3);
    expect(
      screen.getByLabelText('Application field status counts'),
    ).toHaveTextContent('6 matched · 1 not applicable');
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
    const fieldResults = screen.getByLabelText('Application field results');
    expect(within(fieldResults).getByText('Review')).toBeVisible();
    expect(within(fieldResults).getByText('Mismatch')).toBeVisible();
    expect(within(fieldResults).getByText('Not found')).toBeVisible();
    expect(screen.getByText('Not detected')).toBeVisible();
    expect(screen.getAllByText(/manual review/i).length).toBeGreaterThan(0);
  });

  it('requires country only for imported products and renders its result', async () => {
    render(<LabelOcrWorkflow />);
    enterApplicationValues();
    fireEvent.click(screen.getByLabelText('Yes'));
    const country = screen.getByLabelText('Country of origin');
    expect(country).toBeRequired();
    fireEvent.change(country, { target: { value: 'France' } });
    expect(country).toHaveValue('France');

    fireEvent.click(screen.getByLabelText('No'));
    expect(
      screen.queryByLabelText('Country of origin'),
    ).not.toBeInTheDocument();
  });

  it('submits and displays an imported country match', async () => {
    const importedPayload = {
      ...successfulPayload,
      expected: {
        ...successfulPayload.expected,
        imported_product: true,
        country_origin: 'France',
      },
      results: {
        ...successfulPayload.results,
        country_origin: fieldResult(
          'country_origin',
          'match',
          'France',
          'FRANCE',
        ),
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => importedPayload });
    vi.stubGlobal('fetch', fetchMock);
    render(<LabelOcrWorkflow />);
    completeForm();
    fireEvent.click(screen.getByLabelText('Yes'));
    fireEvent.change(screen.getByLabelText('Country of origin'), {
      target: { value: 'France' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Verify Label' }));

    const countryHeading = await screen.findByRole('heading', {
      name: 'Country of origin',
    });
    const countryResult = countryHeading.closest('article');
    expect(countryResult).not.toBeNull();
    expect(within(countryResult!).getByText('Match')).toBeVisible();
    const body = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(body.get('imported_product')).toBe('true');
    expect(body.get('country_origin')).toBe('France');
  });

  it('renders accessible Government Warning component results and evidence', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue({ ok: true, json: async () => successfulPayload }),
    );
    render(<LabelOcrWorkflow />);
    completeForm();
    fireEvent.click(screen.getByRole('button', { name: 'Verify Label' }));

    const warning = await screen.findByRole('region', {
      name: 'Government Health Warning',
    });
    expect(
      within(warning).queryByText(/Automated warning checks passed/),
    ).toBeNull();
    expect(
      within(warning).getByText('Manual physical confirmation required.'),
    ).toBeVisible();
    expect(within(warning).getByText('Warning found')).toBeVisible();
    expect(within(warning).getByText('Required wording')).toBeVisible();
    expect(within(warning).getByText('Heading boldness')).toBeVisible();
    expect(
      within(warning).getByText('Legibility / contrasting background'),
    ).toBeVisible();
    expect(within(warning).getByText('Type-size requirement')).toBeVisible();
    expect(
      within(warning).getByText('Maximum characters per inch'),
    ).toBeVisible();
    expect(
      within(warning).getByRole('heading', {
        name: 'Deterministic text checks',
      }),
    ).toBeVisible();
    expect(
      within(warning).getByRole('heading', { name: 'Image-based evidence' }),
    ).toBeVisible();
    expect(
      within(warning).getByRole('heading', {
        name: 'Manual physical confirmation',
      }),
    ).toBeVisible();
    expect(
      within(warning).getAllByText(/trustworthy scale/i).length,
    ).toBeGreaterThan(0);
    fireEvent.click(
      within(warning).getByText('Inspect localized warning evidence'),
    );
    expect(within(warning).getByText(/GOVERNMENT WARNING:/)).toBeVisible();
    expect(within(warning).getByText(/Mean OCR confidence 92%/)).toBeVisible();
  });

  it('explains when only physical warning checks remain manual', async () => {
    const checks = Object.fromEntries(
      Object.entries(warningChecks).map(([name, check]) => [
        name,
        {
          ...check,
          status: ['type_size', 'characters_per_inch'].includes(name)
            ? 'review'
            : 'match',
        },
      ]),
    );
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ...successfulPayload,
          government_warning: {
            ...successfulPayload.government_warning,
            automated_status: 'match',
            manual_confirmation_required: true,
            checks,
          },
        }),
      }),
    );
    render(<LabelOcrWorkflow />);
    completeForm();
    fireEvent.click(screen.getByRole('button', { name: 'Verify Label' }));
    // A clean label with only physical measurements outstanding shows a plain
    // Match badge and a separate, non-competing physical-confirmation note -
    // not a Review badge and not a combined "some visual requirements" line.
    expect(
      await screen.findByText(
        'Physical Government Warning measurements require manual confirmation.',
      ),
    ).toBeVisible();
    const region = screen.getByRole('region', {
      name: 'Government Health Warning',
    });
    const headerBadge = region.querySelector(
      '.warning-section-heading .status-label',
    );
    expect(headerBadge).toHaveTextContent('Match');
    expect(
      within(region).getByText('Additional physical confirmation required.'),
    ).toBeVisible();
    // The clean-automated-pass case shows only the specific note, not also
    // the generic "Manual physical confirmation required." paragraph.
    expect(
      within(region).queryByText('Manual physical confirmation required.'),
    ).toBeNull();
    expect(within(region).queryByText('Review')).toBeNull();
    const manualLabels = within(region).getAllByText('Manual confirmation');
    expect(manualLabels).toHaveLength(2);
    for (const label of manualLabels) {
      expect(label.closest('article')).toHaveClass('manual-physical');
      expect(label.closest('article')).not.toHaveClass('status-review');
    }
  });

  it('shows warning wording and capitalization mismatches as text', async () => {
    const payload = {
      ...successfulPayload,
      government_warning: {
        ...successfulPayload.government_warning,
        overall_status: 'mismatch' as const,
        localized_text: 'Government Warning: altered wording',
        checks: {
          ...warningChecks,
          wording: warningCheck(
            'mismatch',
            'The extracted warning has missing or changed text.',
          ),
          heading_capitalization: warningCheck(
            'mismatch',
            'OCR represents the heading in mixed case.',
          ),
        },
      },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => payload }),
    );
    render(<LabelOcrWorkflow />);
    completeForm();
    fireEvent.click(screen.getByRole('button', { name: 'Verify Label' }));

    const warning = await screen.findByRole('region', {
      name: 'Government Health Warning',
    });
    expect(within(warning).getAllByText('Mismatch')).toHaveLength(3);
    expect(within(warning).getByText(/missing or changed text/i)).toBeVisible();
    expect(within(warning).getByText(/mixed case/i)).toBeVisible();
  });

  it('renders a warning-not-found state without hiding application results', async () => {
    const missingChecks = Object.fromEntries(
      Object.keys(warningChecks).map((name) => [
        name,
        warningCheck(
          'not_found',
          'No reliable Government Warning evidence was located.',
        ),
      ]),
    );
    const payload = {
      ...successfulPayload,
      government_warning: {
        ...successfulPayload.government_warning,
        overall_status: 'not_found' as const,
        localized_text: null,
        bounding_box: null,
        checks: missingChecks,
      },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => payload }),
    );
    render(<LabelOcrWorkflow />);
    completeForm();
    fireEvent.click(screen.getByRole('button', { name: 'Verify Label' }));

    const warning = await screen.findByRole('region', {
      name: 'Government Health Warning',
    });
    expect(within(warning).getAllByText('Not found').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Application field results')).toBeVisible();
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
  fireEvent.change(screen.getByLabelText('Producer / bottler name'), {
    target: { value: 'Old Tom Distillery LLC' },
  });
  fireEvent.change(screen.getByLabelText('Producer / bottler address'), {
    target: { value: 'Louisville, KY' },
  });
}

function completeForm() {
  enterApplicationValues();
  fireEvent.change(screen.getByLabelText('Choose label image'), {
    target: { files: [labelFile] },
  });
}
