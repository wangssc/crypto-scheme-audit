# crypto-scheme-audit

A local command-line checker for Chinese cryptographic application scheme documents
(密码应用方案). It reads a `.docx`, checks its chapter structure and indicator coverage
against **GB/T 39786-2021 Level 3**, and prints a report.

No network. No telemetry. No file uploads. The document never leaves your machine.

---

## What this actually is

It is a **structural linter**, not a security review.

If you write cryptographic application schemes for Chinese MLPS/密评 processes,
you know the failure mode: the technical design is fine, but chapter 5.3 is missing
three of the nine required elements, the indicator table has 38 rows instead of 41,
and somewhere in the self-assessment column it says "符合" when it should say
"设计满足". None of these are hard to fix. All of them get the document sent back.

This tool finds those. That is the entire scope.

## What it does NOT do

Read this part before trusting the score.

- **It does not judge whether the scheme is secure.** It checks whether the document
  is structurally complete. A perfect score means "nothing obviously missing in the
  structure", not "this system is safe".
- **It does not verify cryptographic products.** If your document claims a product
  exists and is certified, the tool takes your word for it.
- **It does not read images.** Screenshots, diagrams and scanned tables are invisible
  to it. Anything that only exists as a picture is not checked.
- **It does not support PDF or `.doc`.** `.docx` only. Scanned PDFs are out of scope
  entirely — there is no OCR.
- **It does not replace a human reviewer.** Cross-chapter consistency (does every
  protected object in chapter 3 have a corresponding design in chapter 5?) needs
  semantic understanding. The tool can only hint at it, and hints are not scored.

## Install

```
pip install python-docx
```

That is the only dependency. Python 3.8+.

## Usage

```bash
python audit.py 方案.docx                    # text report
python audit.py 方案.docx --markdown         # markdown report
python audit.py 方案.docx --json             # machine-readable
python audit.py 方案.docx --markdown -o r.md # write to file
python audit.py 方案.docx --fail-on critical # CI: exit 1 on critical findings
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | no critical findings |
| 1 | critical findings present (only when `--fail-on` is set) |
| 2 | input unreadable (missing / not a docx / encrypted) |

Note: `--fail-on` defaults to `none`, so a plain run always exits 0.
For CI, pass `--fail-on critical`.

## What it checks

### Structure (S-01 – S-06)

The eight chapters required by GB/T 43207-2023 Annex A:

```
1 背景          2 系统概述      3 需求分析      4 目标与原则
5 密码应用设计   6 安全管理      7 合规性分析    8 实施保障
```

Plus subsection completeness: 2.1–2.5, 3.1–3.3, 5.1–5.5, the nine elements
a)–i) under 5.3, and the ten key-management stages a)–j).

Chapter titles are matched by "chapter number + fixed name", so
`一、背景`, `1. 项目背景` and `第一章 背景` all work. Body text that merely
mentions 背景 does not count as a chapter.

### Indicator coverage (C-01 – C-06)

Looks for the indicator table (technical 22 rows + management 19 rows = 41 rows)
and checks:

- does the table exist at all (reports critical if not — it does not guess)
- row count
- whether each of the 22 technical clauses is present
- whether each of the 19 management clauses is present
- whether the level column matches 应 / 宜 / 可 from the standard

The 19 management rows are checked clause-by-clause against **8.5 – 8.8** of
the third-level requirements, and **all 19 are 应 (mandatory)**. Writing 宜 for
one of them gets reported.

> Easy mistake: third-level management requirements are **8.5–8.8**, not
> 9.1–9.8. Section 9 is the fourth level; a table copied from a level-4
> template goes wrong starting right there.

### Wording (W-01 – W-02)

Flags 符合 in the self-assessment. At scheme stage there is no implementation
evidence, so "符合" (compliant) is a conclusion you cannot support yet.
Acceptable phrasings: 设计满足 / 满足 / 依赖云商提供 / 待验证 / 部分满足 / 不适用.

Excluded from flagging, so you can write them safely:

| Phrasing | Why it is fine |
|---|---|
| 不符合 | opposite meaning — an honest gap statement |
| 整改后符合 | explicit precondition |
| 符合性分析 | a noun, not an assertion |
| 符合 GB/T ×××× | claims conformance to a writing standard |

The last two are exclusions I added beyond the written spec. Without them a
normal document produces dozens of false positives (the chapter title
"合规性分析", standard references everywhere), and a report nobody reads is
worse than no report.

### Format (F-01 – F-04)

Not scored — cosmetic. Ragged tables, headings typed by hand instead of using
Word heading styles, malformed clause numbers (`8.2b` / `8.2-B` instead of `8.2 b)`),
and leftover placeholders (`TODO` / `XXX` / `待补充` / `【】`).

## Scoring

```
penalty = critical 20 / warn 6 / hint 0, summed
score   = round(100 × e^(−penalty / 90))
if any critical: score capped at 65
```

| Situation | Score |
|---|---|
| clean | 100 |
| 1 warn | 94 |
| 3 warns | 82 |
| 1 critical | 65 (capped) |

If the document does not look like a scheme at all (fewer than 5 of the 8 chapters
found), the result is **`not assessed`** — score is `null`, not zero.
That is deliberate: "could not evaluate" and "evaluated as bad" are different
outcomes and should not look the same.

## Privacy

The tool reads the `.docx` locally and prints findings. Findings reference
chapter names, clause numbers and table indices only — **never sentences from
your document**. There is a test for this (`test_report_contains_no_source_snippet`),
because it is exactly the kind of property that quietly breaks during refactoring.

Nothing is written except the report file you ask for with `-o`.

## Tests

```bash
python tests/make_fixtures.py    # generate the five fixture docx
python -m pytest tests/ -q
```

Fixtures cover: a complete scheme, a scheme missing chapter 5, one with a wrong
indicator level, one with "符合" in the self-assessment, and an unrelated document.

## License

MIT.
