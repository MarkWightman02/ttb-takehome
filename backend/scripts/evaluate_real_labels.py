#!/usr/bin/env python3
import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evaluation.real_labels import run_real_label_evaluation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run repository real-label fixtures through real local Tesseract."
    )
    parser.add_argument(
        "--examples-dir",
        type=Path,
        default=REPOSITORY_ROOT / "examples",
        help="Directory containing same-stem image and application JSON pairs.",
    )
    parser.add_argument("--json", action="store_true", help="Print the complete JSON report.")
    args = parser.parse_args()
    report = asyncio.run(run_real_label_evaluation(args.examples_dir.resolve()))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_summary(report)
    return (
        1
        if report["ocr_failures"]
        or report["processing_failures"]
        or report["false_confident_matches"]
        else 0
    )


def _print_summary(report: dict[str, object]) -> None:
    counts = report["field_status_counts"]
    assert isinstance(counts, dict)
    print(
        f"Cases: {report['total_cases']} | OCR invocations: {report['ocr_invocations']} | "
        f"OCR failures: {report['ocr_failures']} | "
        f"processing failures: {report['processing_failures']}"
    )
    print("Field statuses: " + " | ".join(f"{name}: {value}" for name, value in counts.items()))
    print(
        f"False confident matches: {report['false_confident_matches']} | "
        f"missed expected matches: {report['missed_expected_matches']}"
    )
    latency = report["latency_ms"]
    assert isinstance(latency, dict)
    for stage in ("preprocessing_ms", "ocr_ms", "analysis_ms", "total_ms"):
        values = latency.get(stage)
        if not isinstance(values, dict):
            continue
        print(
            f"{stage.removesuffix('_ms')}: median {values['median']:.1f} ms | "
            f"p90 {values['p90']:.1f} ms | slowest {values['slowest']:.1f} ms"
        )
    cases = report["cases"]
    assert isinstance(cases, list)
    for case in cases:
        if not isinstance(case, dict):
            continue
        if case.get("error"):
            print(f"- {case['name']}: ERROR {case['error']}: {case.get('message', '')}")
            continue
        results = case["results"]
        assert isinstance(results, dict)
        fields = ", ".join(
            f"{field}={result['status']} ({result.get('extracted_raw') or 'none'})"
            for field, result in results.items()
        )
        print(f"- {case['name']}: {fields}")


if __name__ == "__main__":
    raise SystemExit(main())
