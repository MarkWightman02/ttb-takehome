# Verification logic

A short explanation, for a technical reviewer, of how a result status is decided and why the tool is deliberately cautious. This is the summary; [architecture.md](architecture.md) holds the full implementation reasoning, and [USER_GUIDE.md](USER_GUIDE.md) covers what the statuses mean to someone using the tool.

## The pipeline

```text
Application information (typed by the reviewer)
        +
Submitted label image
        |
        v
Image validation and preprocessing
        |
        v
Label text reading (local Tesseract, word-level geometry and confidence)
        |
        v
Structured extraction        -> candidate values per field, with evidence
        |
        v
Normalization and comparison -> match / review / mismatch / not_found
        |
        v
Government Warning analysis  -> its own set of checks
```

Extraction and comparison are separate stages on purpose: the label is read first, then compared. That ordering is what makes the next principle enforceable.

## Core principles

**The application values never influence what is read from the label.** Extraction produces candidates from the image alone. The expected values are only used afterward, at the comparison step. Even the targeted re-read step — which crops a region and reads it again at higher fidelity when a field is uncertain — plans those crops from image geometry, never from the expected text. The tool cannot "find" a value on a label because it was told to expect it.

**Uncertainty becomes `review`, not a match.** Exact equality after normalization is a match. Similarity is used only to decide whether a non-match is close enough to be worth a human look (`review`) or clearly different (`mismatch`). There is no threshold at which a near-miss is silently promoted to a match. A false confident match is treated as the most serious possible error, so the design trades extra `review` results for never producing one.

**Absence of evidence is reported as absence.** When no reliable candidate is found, the result is `not_found` — not a guess, and not an error. This is a normal outcome for a panel that was not uploaded or text that could not be read.

## Field comparison

**Text fields** (brand name, class/type, producer name, address) are normalized before comparison: Unicode compatibility normalization, case folding, whitespace collapse, conservative punctuation handling, and apostrophe equivalence. So `STONE'S THROW` matches `Stone's Throw`. Beyond exact normalized equality, sequence similarity decides only between `review` and `mismatch`.

**Numeric fields** (ABV, net contents) are compared exactly after numeric normalization — ABV as a percentage, volumes converted to millilitres. There is no tolerance band: `45` does not match `45.5`. Supported volume units are metric plus the label-relevant US pint and fluid-ounce forms; an unsupported unit is rejected rather than approximated.

**Multiple distinct candidates always produce `review`**, even when one of them matches the expected value. If a label shows two different ABV figures, the tool will not pick the convenient one.

**Producer/bottler name and address** require a responsible-party cue on the label — *Bottled by*, *Produced by*, *Imported by*, and similar, including compound forms. A company name with no such relationship is not assumed to be the producer. Partial address containment is `review`; a conflicting state is `mismatch`.

**Country of origin** is checked only when the application marks the product as imported. Domestic products return `not_applicable`, which is excluded from the overall status.

## Government Warning

The warning is analyzed separately from the application fields, and its checks fall into two groups.

**Checkable from the image (eight checks)** — presence, prescribed wording, heading capitalization, heading emphasis, body text formatting, continuity, layout, readability. These roll up into a single `automated_status`, which is what drives the overall result.

**Not checkable from an image (two checks)** — minimum physical type size and maximum characters per printed inch. These describe the physical printed label. A raster image carries no trustworthy real-world scale, and the implementation refuses to infer one from DPI metadata, pixel counts, or container volume. They are reported with the applicable regulatory tier and a separate `manual_confirmation_required` flag, and they never degrade the automated result.

Wording comparison distinguishes plausible misreading from substantive change: bounded differences that look like imperfect text recognition become `review`, while confidently absent, replaced, or reordered clauses become `mismatch`. It is not a single permissive fuzzy threshold.

## Overall status precedence

The top-level summary is decided in this order:

1. **Mismatch** — any application field is a mismatch, or the warning's automated status is a mismatch.
2. **Review** — any field is `review` or `not_found`, or the warning's automated status is `review` or `not_found`.
3. **Match, with manual physical confirmation outstanding** — everything checkable passed, and physical measurements still require manual confirmation. This is the normal clean outcome for an image upload.
4. **Match** — everything passed with nothing outstanding.

The important property is that an outstanding *physical* confirmation never masks a real problem and never manufactures one. It is ranked below every genuine finding, and it is surfaced as a separate note rather than folded into the status. `not_applicable` results are excluded from aggregation entirely.

## What this is not

Results are decision support for a human reviewer. The tool does not approve or reject an application, does not determine legal compliance, and does not claim that a physical label meets a printed-dimension requirement. Its confidence signals and image heuristics are evidence, not proof of typeface, physical dimensions, or legibility under ordinary viewing conditions.
