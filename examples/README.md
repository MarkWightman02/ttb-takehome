# Real TTB sample regression fixtures

These TTB-provided educational/sample label images are included to exercise the prototype's real-Tesseract and spatial-layout behavior. Each companion JSON file represents the expected application input used by the verification workflow. The six pairs are a small regression set, not a comprehensive benchmark or an estimate of real-world accuracy.

The runner decodes image content rather than trusting filename extensions. `FBN.jpg`, `MHB.jpg`, and `WINE.jpg` contain PNG data. This is retained as received so upload/content validation and evaluation provenance remain visible.

Some expected application values are not explicit responsible-entity statements on the visible artwork. In particular, FBN and MHB identify a brand and location but do not show a producer/bottler role cue. The evaluator preserves `not_found` for those producer/address checks instead of forcing a match. MHB visibly includes `500 ML`, but the current low-resolution OCR output does not contain a reliable volume token, so that field also remains `not_found`.

Run the set with:

```sh
python backend/scripts/evaluate_real_labels.py
```

Use `--json` for raw OCR, candidate evidence, field and Government Warning checks, decoded-format metadata, and per-stage timings.
