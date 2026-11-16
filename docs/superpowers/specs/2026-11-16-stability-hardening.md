# Stability hardening scope

Approved by the user on 2026-11-16 after the read-only audit of v0.3.0 (`b03e5cf`).

## Goal

Improve reliability without adding/removing user features or changing collection commands, policy interpretation, report semantics, annotation schemaVersion 1, approval policy, or supported workflows.

## Required fixes

1. Bound SSH channel/PTY/shell preparation by the existing collection deadline and cancellation, and close partially initialized connections on failure.
2. Serialize known_hosts read/check/add/replace across processes without accepting changed keys or bypassing explicit trust.
3. Preserve distinct controllers' raw evidence when display names or sanitized filenames collide; repeat writes for one controller remain deterministic.
4. Retain the last successful Web artifacts when the next request fails, clearly distinguishing the current failure from previous results.
5. Ignore obsolete asynchronous annotation reads/imports, restore correct unsaved-state tracking, and keep invalid over-limit edits out of committed project state.
6. Keep report artifact publication and completion metadata consistent on failure; retain existing rollback guarantees and primary exception evidence.
7. Stream Role network worksheets instead of materializing every row, retaining row validation, duplicates, ordering and error summaries.
8. Select exact-version GUI/Web packages; recover interrupted embedded Python downloads; tolerate transient initial EXE copy locks; handle literal build paths including brackets.

## Boundaries and release

- No real WLC, corporate data, credentials, user Windows browser or printing validation. Automated synthetic regressions and hosted Windows packaging checks are in scope.
- No new runtime dependency unless a necessary fix cannot be implemented safely with existing dependencies/stdlib.
- Preserve existing error classification, partial collection semantics, host-key strictness and offline behavior.
- v0.3.1 is a patch release for operationally significant bug fixes. Main merge and official release publication are already authorized by the user.
