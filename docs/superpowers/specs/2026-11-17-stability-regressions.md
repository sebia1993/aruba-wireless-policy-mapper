# v0.3.2 Stability Regression Specification

## Approved scope

The user approved implementing the eight reproduced audit findings, followed by automated validation, independent review, main merge and an official patch release. Real company devices and user-operated Windows/printing checks are outside this work.

## Required outcomes

1. Recognized CLI rejection responses are failed commands, not successful nonempty output. Preserve raw evidence and distinguish required failure from optional partial completion. Ordinary descriptions containing words such as `error` must remain valid.
2. Command completion requires an escaped, anchored device prompt boundary within the existing deadline. Delayed chunks must be included; timeout or loss of framing must prevent bytes from contaminating the next command.
3. After saving annotation JSON or HTML, later unsaved edits must remain explicitly recoverable from the saved revision and the original revision. Keep schemaVersion 1 and the existing snapshot/project/conflict safeguards. Storage failure must remain visible and must not destroy a pending recovery draft.
4. The portable Windows host-key launcher must invoke the functioning package entry point. Package verification must execute an offline invalid-address case and check its nonzero validation result.
5. Failed optional collection commands or disconnects must produce a non-OK diagnostic outcome, consistent across CLI, GUI, JSON, HTML and logs. Preserve reports and successful evidence. Do not turn unrelated informational warnings into failures.
6. Registered diagnostic codes must survive redaction in structured events and logs; device identities, addresses and secrets remain masked.
7. Impact scope must distinguish controllers with the same display name using the existing stable identity. Ambiguous legacy data must not be attributed to an arbitrary device.
8. Cancellation during a required-command timeout must retain the failure evidence and report cancellation, with normal connection cleanup.

## Compatibility

Preserve collection command strings, policy interpretation, report meaning and formats, annotation schemaVersion 1, strict host-key approval and existing successful workflows. Add no unrelated feature and no live device access. Keep the patch localized, with meaningful synthetic regressions for each reproduced error path.

## Acceptance

Each fix has a failing-before/passing-after regression. Integrated Python and JavaScript suites and existing hosted Windows packaging gates pass. Independent review has no unresolved important findings. Release v0.3.2 resolves to the reviewed merged source and publishes the existing Windows ZIP, SHA256 sidecar and SBOM artifacts.
