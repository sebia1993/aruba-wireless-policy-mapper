# Stability Hardening Implementation Plan

> **For agentic workers:** Use Superpowers development and review workflows. Execute the approved audit fixes continuously; user approval already covers implementation, main merge and official release.

**Goal:** Resolve the audited failure paths while preserving existing functionality.

**Architecture:** Keep fixes inside their current ownership boundaries: connection lifecycle, annotation editor, persistence, and packaging. Add focused synthetic regressions, then run the integrated suite and existing Windows release gates.

**Tech Stack:** Python 3.11+, Netmiko/Paramiko, Streamlit, openpyxl, offline JavaScript/JSDOM, Windows PowerShell.

**Spec:** `docs/superpowers/specs/2026-11-16-stability-hardening.md`

## Global Constraints

- Preserve collection commands, policy interpretation, report meaning, annotation schemaVersion 1 and explicit host-key approval.
- Use synthetic data only; actual WLC/user Windows/printing verification is excluded.
- Do not modify another task's files. Root integrates commits, version/docs, PR, merge and release.
- Add regression tests for concrete failures; do not add source-text-only or implementation-mirroring tests.

## Review Focus

- Cancellation during SSH connection preparation must release real channel waits and not leave detached background work.
- Cross-process key updates must preserve both entries and reject a changed key after acquiring the lock.
- Stale file Promise completion/rejection must not overwrite a new annotation project or its status.
- Failed Web retries must show the new failure with correctly identified old successful artifacts.
- Report rollback and filename collisions must preserve earlier evidence on Windows semantics too.

### Task 1: SSH lifecycle and known_hosts

Files: `collector.py`, `ssh_connection.py`, `hostkeys.py`, focused related tests; a small internal lock helper if needed.
Interfaces: existing collection API/commands and strict host-key client remain compatible. New optional private deadline/cancellation plumbing must not leak into Netmiko kwargs.

- [ ] Add failing regressions for stalled PTY/shell preparation, cancellation/deadline, constructor failure cleanup, concurrent approvals and changed-key recheck.
- [ ] Implement bounded lifecycle cleanup and cross-process key update serialization.
- [ ] Run focused connection/collector/host-key tests; report exact commands/results for review.

### Task 2: Annotation workspace state

Files: `static/annotation_editor.js`, `tests/js/annotation_editor.test.js`; core/test fixtures only if necessary.
Interfaces: same exported editor API and schemaVersion 1. Preserve existing import/reuse/export semantics.

- [ ] Add failing regressions for out-of-order file reads, stale import/rejection, same-revision recovery unsaved warning and aggregate text-limit edits.
- [ ] Guard asynchronous results by request/project generation; track dirty state across recovery; validate edits before commit.
- [ ] Run Node editor tests and existing annotation suite; report evidence for review.

### Task 3: Windows packaging reliability

Files: three `build_windows_*.ps1` scripts, focused `tools` helpers and packaging tests. Root owns workflows/release metadata; coordinate any necessary workflow hook.
Interfaces: preserve current package layout/entry points, locked dependencies, exact current project version.

- [ ] Add behavioral tests using temporary packages/caches and an injected transient copy failure where possible; Windows-only checks must run under hosted CI.
- [ ] Select exact-version packages, validate/download runtime cache atomically, retry initial EXE copy and use literal path handling.
- [ ] Run available focused tests; report Windows-only limitations and required CI hook.

### Task 4: Evidence and output preservation

Files: `report.py`, `atomic_io.py`, `app.py`, `role_networks.py`, related tests.
Interfaces: existing report return keys and filenames for non-colliding controllers remain compatible; no new user feature or schema.

- [ ] Add failing tests for same-name/sanitized-name raw collisions and repeated writes.
- [ ] Add failing app-state tests for invalid/busy/failed retries and successful replacement.
- [ ] Add final-status failure/rollback and sparse-sheet streaming regressions.
- [ ] Implement minimal persistence/state fixes; run focused tests.

### Task 5: Integrated review and v0.3.1 release

Files: package version, changelog/release notes, concise validation record and Release workflow body.

- [ ] Perform independent scoped and whole-change review; fix important findings.
- [ ] Run integrated Python/Node tests; update version/docs to v0.3.1.
- [ ] Push isolated branch, create PR and pass existing hosted Windows validation.
- [ ] Merge to main, run the official Release workflow and verify non-draft/non-prerelease assets and target commit.
- [ ] Report completed work, next work and progress, excluding user validation.
