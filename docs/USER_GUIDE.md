# User guide

This guide is for the person reviewing a label application. It explains how to use the tool and how to read its results. You do not need to understand how the software works.

- To start the tool, see the Quick Start in the [README](../README.md), or use the hosted demo at [https://ttb.markwightman.org](https://ttb.markwightman.org).
- If something does not work, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
- To check many labels at once, see [BATCH_VERIFICATION.md](BATCH_VERIFICATION.md).

## What the tool does

You type in the information that came with the application. You upload the label artwork that was submitted with it. The tool reads the text it can see on the label image, compares it to what you typed, and shows you where the two agree, where they differ, and where it could not tell.

It is a checking aid. It does not approve or reject applications, and it does not make a legal compliance decision. A person still decides.

## Before you begin

You will need:

- The application information (brand name, class/type, alcohol content, net contents, producer/bottler name and address, and whether the product is imported).
- The label artwork that was submitted with the application, saved as an image file.
- A supported image format: **PNG, JPEG, or WebP**, up to **10 MB**.

## Single-label walkthrough

### 1. Open Label Verification

Open the tool. The page is laid out as four numbered steps, top to bottom.

### 2. Enter the application information (step 1)

Fill in each box using the values from the application:

| Field | What to enter |
| --- | --- |
| Brand name | The brand name as it appears on the application, for example `Stone's Throw`. |
| Class/type designation | The class or type of beverage, for example `Kentucky Straight Bourbon Whiskey`. |
| Alcohol content / ABV (%) | The alcohol by volume as a number only, for example `45`. Do not type the percent sign. |
| Net contents | The stated contents including the unit, for example `750 mL`. |
| Producer / bottler name | The responsible company named on the application, for example `Example Distillery LLC`. |
| Producer / bottler address | The city and state (or full address) for that company, for example `Louisville, KY`. |

You do not need to match the label's capitalization. `STONE'S THROW` and `Stone's Throw` are treated as the same.

### 3. Indicate imported or domestic

Choose **Yes** or **No** for *Imported product*.

### 4. Enter country of origin if applicable

If you chose **Yes**, a *Country of origin* box appears. Enter the country from the application, for example `France`. If the product is domestic, this box does not appear and that check is reported as *Not applicable*.

### 5. Upload the submitted label (step 2)

Select **Choose label image**, or drag the image file onto the upload area. The file name and a preview appear once it is selected.

### 6. Select Verify Label (step 3)

The tool reads the label and compares it. This normally takes a few seconds.

### 7. Review the results (step 4)

Results appear in three parts:

1. A summary banner at the top with an overall outcome and a count, for example `6 matched · 1 not applicable`.
2. A card for each application field, showing what you entered next to what was found on the label.
3. A **Government Health Warning** section with its own checks.

## Understanding results

Each field card shows the value from the **Application**, the value found on the **Label**, and a status.

| Status | What it means |
| --- | --- |
| **Match** | The label supports what you entered. |
| **Review** | The tool found something plausible but could not confirm it confidently. Not a failure — it needs your eyes. |
| **Mismatch** | The label and the application appear to genuinely differ. |
| **Not found** | The tool could not find this information on the label image. |
| **Not applicable** | This check does not apply, for example country of origin on a domestic product. |

### Examples

A match:

```text
Alcohol content / ABV
Application:  45%
Label:        45% Alc./Vol.
Status:       Match
```

A mismatch:

```text
Alcohol content / ABV
Application:  45%
Label:        43%
Status:       Mismatch
```

A review:

```text
Brand name
Application:  Stone's Throw
Label:        STONE'S THROW  (detected twice in different styles)
Status:       Review
```

**Review does not mean the label failed.** It means the tool is deliberately not guessing. It is designed to hand you an uncertain case rather than give you a confident answer that might be wrong.

## Government Health Warning

The warning is checked separately, in three groups.

**Warning text** — whether the warning is present, whether the wording matches the prescribed statement, and whether the `GOVERNMENT WARNING` heading is capitalized.

**Warning presentation** — heading emphasis, body text formatting, whether the statement runs continuously, its layout, and its readability against the background.

**Physical measurements** — minimum type size and maximum characters per inch. These are shown with a **Manual confirmation** label, not a status.

### Why physical measurements say "Manual confirmation"

Type size in millimeters and characters per printed inch are properties of the **physical printed label**. An ordinary image file has no reliable real-world scale — the same picture can be printed at any size — so the tool does not guess at them.

These two items are shown for reference with the applicable limit, and they must be confirmed against the physical label. **They do not mean anything is wrong**, and they do not turn an otherwise clean result into a failure. A label whose checkable items all pass shows **Match**, with a separate, neutral note that physical measurements still need manual confirmation.

The tool does not make a final regulatory decision on the warning or anything else.

## What to do when a result says Review

1. Look at the label image yourself and find the item in question.
2. Re-check what was typed into the application field — a stray character or extra word is a common cause.
3. Consider the image: low resolution, glare, heavy stylization, or a tight crop can all make text hard to read.
4. If the item is legible to you and matches, treat it as verified. The tool is flagging its own uncertainty, not asserting a problem.

## What to do when a result says Mismatch

1. Compare the **Application** value and the **Label** value shown on the card.
2. Confirm the application value was not mistyped.
3. If both are correct as shown, you have a genuine discrepancy to investigate.

## What to do when a result says Not found

1. Confirm the information is actually present on the artwork you uploaded — it may be on a panel that was not included.
2. For producer/bottler name and address, the tool looks for a responsible-party cue such as *Bottled by* or *Imported by*. If the label shows a name with no such relationship, the tool reports *Not found* instead of assuming a role.
3. Re-upload a clearer or more complete image if the text is present but hard to read.

## Image tips

- Upload the label artwork itself, at the best quality you have.
- Include all panels that carry required information. If the warning is on the back panel, that panel needs to be in the image.
- Avoid screenshots that include browser toolbars, window borders, or desktop background.
- Avoid heavily compressed or downscaled copies — compression artifacts make text harder to read.
- Do not crop off text you need checked.

The tool applies modest, automatic image cleanup, but it cannot rescue an unreadable image. Photographs of curved bottles, strong glare, and steep angles will produce more *Review* and *Not found* results.

## Related documentation

- [Batch verification](BATCH_VERIFICATION.md) — checking many labels at once.
- [Troubleshooting](TROUBLESHOOTING.md) — when something does not work.
- [Verification logic](VERIFICATION_LOGIC.md) — how results are decided, in brief.
