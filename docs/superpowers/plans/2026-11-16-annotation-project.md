# Implementation plan

Approved scope: [specification](../specs/2026-11-16-annotation-project.md).
Base commit: `57960fbc08a981a9e7f2892244c8658024b4288b`.
Branch: `feature/annotation-project-reuse-export`.

## Work packages and progress weights

1. Snapshot DTO, safe serialization and controller identity — 20%.
2. Validation, conservative reuse, orphan preservation and export model — 25%.
3. Editor, project open/save, legacy import and explicit recovery — 25%.
4. Offline XLSX, separate PDF view and common export scope — 20%.
5. Integration, automated regression checks, documentation and draft PR — 10%.

Manual validation with actual controllers, Windows, company files and the
user's printing environment is explicitly outside this development denominator.

## Ownership and interfaces

Independent work uses the shared contract in the specification. The snapshot
worker owns `annotation_project.py` and its Python tests. The core worker owns
`static/annotation_core.js` and its Node tests. The export worker owns
`static/annotation_export.js`, its tests and the ExcelJS vendor/license files.
The coordinator owns report integration, the editor, controller isolation,
legacy import, documentation and all commits. No worker edits another worker's
files. Independent implementation is parallelized under the session's explicit
parallel-work instruction; integration remains sequential.

## Verification gates

- Baseline: 191 Python tests passed before changes.
- Regressions: same names on different controllers; duplicate rules; raw action
  suffix changes; rule insertion/reorder; alias changes; partial collection;
  malformed/future-version project; unsafe imported HTML; stale cache and
  deletion restoration; disabled/quota-failed storage; scope consistency.
- Read generated XLSX with openpyxl; confirm five sheets, literal formulas,
  Korean and multiline notes, long-text continuation, row/scope counts.
- Run fresh Python suite, Node core/export/editor tests and JavaScript syntax
  checks. Independently review the full diff and resolve material issues.
- Update Korean usage/developer documentation, push the feature branch and
  open a draft PR. Do not merge or issue a release as part of this task.
