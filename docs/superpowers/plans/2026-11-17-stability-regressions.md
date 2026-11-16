# v0.3.2 Stability Regression Implementation Plan

**Goal:** Fix the eight reproduced audit failures and release the verified patch.

**Architecture:** Localize changes to command framing, annotation recovery bookkeeping, diagnostic status/redaction, controller identity selection, and the portable launcher. Independent worktrees allow disjoint tasks to proceed concurrently; integration and release are sequential.

**Tech Stack:** Python, Netmiko/Paramiko, Streamlit, offline JavaScript/JSDOM, Windows CMD/PowerShell, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-17-stability-regressions.md`

## Global Constraints

- Preserve collection command strings, policy interpretation, report meaning and formats, annotation schemaVersion 1, strict host-key approval and existing successful workflows.
- Use synthetic data only; actual company devices and user-operated Windows/printing checks are excluded.
- Keep fixes within task ownership. Root integrates commits, shared interfaces, release metadata, PR, merge and publication.
- Add meaningful failing-before/passing-after regressions. Do not test by grepping source text or mirroring implementation.
- Use current worktree source when running tests; the reusable Python environment has an older editable install.

## Review Focus

Completion boundaries, command-response evidence, cancellation precedence, recovery branch ambiguity, field-specific redaction, duplicate display names, and an executable packaged launcher smoke check.

### Task 1: Reliable command results and cancellation

Files: `src/wlc_role_acl_collector/collector.py`, optional small `command_response.py`, `tests/test_collector.py`, focused new command-response/GUI tests and shared test doubles only as necessary. Do not edit diagnostics or collection-health modules.

Interfaces: preserve public collection API and command strings. Existing CommandOutput success/error/raw output and cancellation markers remain the result contract. If a shared rejection classifier is introduced, report its interface to root for integration.

- [x] Add regressions for recognized CLI rejection on required and optional commands, legitimate descriptions containing error words, delayed response tails, missing completion prompts, no next-command contamination, and cancellation during required-query timeout.
- [x] Verify RED against current behavior before product edits. Prefer an actual Netmiko BaseConnection with a deterministic channel for timing behavior, not a stub that asserts implementation kwargs.
- [x] Frame responses with the actual escaped/anchored device prompt and preserve the existing bounded deadline. Check command echo/context as supported. On unframed timeout, stop or resynchronize the connection before any further command. Raising last_read alone is insufficient.
- [x] Mark recognized device rejections failed while preserving evidence; required failures remain failed and optional failures partial. Preserve cancellation and cleanup when required queries fail after a cancel request.
- [x] Run focused regressions and one Python suite; commit and report exact RED/GREEN commands, results and remaining risks.

### Task 2: Recovery across downloaded revisions

Files: `src/wlc_role_acl_collector/static/annotation_editor.js`, `tests/js/annotation_editor.test.js`, test fixture only if needed. Keep Python annotation-project builder unchanged.

Interfaces: preserve existing editor API and schemaVersion 1. Recovery is explicitly user accepted. Use minimal recovery bookkeeping to retain compatible original and downloaded base anchors; do not merely replace base and orphan original recovery.

- [x] Add failing regressions exercising actual JSON and HTML downloads, later edits, and reopen from the downloaded project with shared same-origin storage.
- [x] Cover repeated saves, continued recovery from original revision, same IDs with different snapshots, storage quota failure, preservation of pending recovery, and branch conflict safeguards.
- [x] Implement recovery anchor registration and reads without changing exported project schema or weakening project/snapshot/revision guards. Handle inability to persist recovery visibly.
- [x] Run focused tests and the full Node annotation suite; commit and report RED/GREEN evidence and chosen branch behavior.

### Task 3: Diagnostic failure truth and safe codes

Files: `diagnostic_mode.py`, `diagnostic_events.py`, `diagnostic_report.py`, `redaction.py` if necessary, related diagnostic/redaction/CLI tests. Do not edit collector.py; root coordinates its result contract.

Interfaces: existing registered diagnostic codes and primary-code consumers remain compatible. Final CollectionResult contains failed CommandOutput records; optional failures and disconnects may not emit progress callbacks. Treat final evidence as authoritative and deduplicate events.

- [x] Add failing regressions for optional rights/user-table/disconnect failures producing non-OK diagnostic status and CLI exit while preserving reports, including missing and duplicate callback events.
- [x] Add failing tests showing known codes survive JSON, HTML and log redaction while IP, credentials, controller names, role and alias details remain masked.
- [x] Reconcile final failures with callbacks; choose existing appropriate failure codes, preserve required-command precedence and successful diagnostic behavior. Do not classify every parse warning as failure.
- [x] Preserve only validated registered code fields through serialization/redaction; do not broadly exempt message text or identifiers.
- [x] Run focused tests and one Python suite; commit and report exact RED/GREEN evidence.

### Task 4: Identity-scoped impact reporting

Files: `collection_health.py`, `annotation_project.py` only for a shared identity import/re-export, optional small `controller_identity.py`, related collection-health/annotation/report tests. Root owns implementation.

- [x] Add failing tests for same display name with different stable IDs, same role names across devices, parsed-result scope, and ambiguous legacy rows.
- [x] Reuse the exact existing stable controller identity semantics; avoid circular imports and ID format changes. Prefer explicit IDs, with conservative fallback for old rows.
- [x] Keep impact roles/SSIDs restricted to the failed device. Run focused tests and commit.

### Task 5: Execute and verify the host-key launcher

Files: `packaging/streamlit_portable/trust_host_key.cmd`, `tools/verify_streamlit_portable_package.py`, relevant tooling/Windows packaging tests. Root owns implementation.

- [x] Add an offline behavior regression for module/launcher invalid-address handling and a package-verifier check that fails for the old silent-success entry point.
- [x] Invoke the actual package entry point. Exercise the packaged launcher with a deliberately invalid host, bypassing interactive pause only for smoke execution; expect validation failure and no network access.
- [x] Run available focused tests. Ensure Windows-only execution is included in the existing package verification/CI gate; commit.

### Task 6: Integration, review and official v0.3.2 release

Files: version metadata, CHANGELOG/RELEASE_NOTES/DEVELOPMENT_LOG, validation records and release workflow body as needed.

- [ ] Integrate reviewed task commits; resolve shared interfaces, run complete Python/Node suites and review the whole change independently.
- [ ] Update patch version and accurate validation/release notes; preserve asset formats and package layout.
- [ ] Push the isolated branch, create PR, pass hosted validation and merge reviewed source to main.
- [ ] Run official Release workflow and verify tag, merged commit, release visibility, ZIP, SHA256 sidecar and SBOM.
- [ ] Report completed work, next work and progress, with excluded user checks clearly scoped.
