#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evaluation.runner import run_evaluation_sync  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the generated TTB label corpus through real local Tesseract."
    )
    parser.add_argument("--json", action="store_true", help="Print the complete JSON report.")
    args = parser.parse_args()
    report = run_evaluation_sync()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_summary(report)
    return 1 if report["ocr_or_processing_failures"] or report["false_confident_matches"] else 0


def _print_summary(report: dict[str, object]) -> None:
    print(
        f"Cases: {report['total_cases']} | checks: {report['total_expectations']} | "
        f"exact statuses: {report['exact_status_checks']} "
        f"({float(report['status_accuracy']):.1%})"
    )
    print(
        f"False confident matches: {report['false_confident_matches']} | "
        f"false mismatches: {report['false_mismatches']} | "
        f"missed matches: {report['missed_matches']}"
    )
    print(
        f"Review results: {report['review_count']} | not found: {report['not_found_count']} | "
        f"OCR/processing failures: {report['ocr_or_processing_failures']}"
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
    differences = [
        case
        for case in report["cases"]
        if isinstance(case, dict) and (case.get("differences") or case.get("error"))
    ]
    print(f"Cases with status differences: {len(differences)}")
    for case in differences:
        print(f"- {case['name']}: {case.get('differences') or case.get('error')}")


if __name__ == "__main__":
    raise SystemExit(main())
