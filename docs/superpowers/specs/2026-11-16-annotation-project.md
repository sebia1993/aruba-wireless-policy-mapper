# Offline annotation projects and reporting

The approved change makes the generated HTML the annotation editor. A versioned
JSON project is the durable source for the collected snapshot and human notes.
Opening a project requires no controller connection. Importing previous notes
keeps the current snapshot and conservatively reconciles annotations. PDF and
real XLSX exports use the same explicit export model and latest edits.

## Required behavior

- Scope controllers by endpoint, port and configuration scope; scope roles,
  aliases, rules, DOM identities and exports by controller. Never join by a
  display name or positional rule index across collections.
- Match full raw rules, retaining action options, within controller/role/ACL.
  Duplicate matches require a choice. Reused notes are not automatically
  reviewed. Changed alias membership, binding order, preceding rules, incomplete
  collection or unknown service semantics require review.
- Preserve unmatched notes. Absence from a partial/unknown collection is not
  evidence of deletion. A schema or validation error must not replace work.
- Files are authoritative. Browser storage is optional recovery only, scoped to
  project/snapshot/base revision; recovery is explicit. Empty notes remain empty.
  Quota/privacy failures never prevent file download or imply successful saving.
- Save/open complete projects, import prior projects or inertly parsed legacy
  commented HTML, and save an annotated HTML copy. Imported HTML is never run.
- Export all policies, selected role(s), or changes/review items independent of
  hidden DOM rows. XLSX has five sheets (보고 요약, Role 설명, ACL 상세,
  변경·확인 사항, Alias 상세),
  literal text cells and continuation rows for overlong text. PDF has a separate
  escaped print view with readable wrapped notes and does not mutate the editor.
- Keep timestamps, project/snapshot IDs, revision and export scope in reports.
  Do not serialize credentials, raw user tables, or opt-out local networks.
- Preserve existing collection and Access Check behavior while fixing controller
  isolation. Actual company-device/Windows validation is left to the user.

## Shared contract (schemaVersion 1)

`format = "aruba-policy-annotations"`. Top-level fields: `format`,
`schemaVersion`, `projectId`, `revision` (integer), `createdAt`, `updatedAt`,
`snapshot`, `annotations`, `unresolvedAnnotations`, `changes`, `importHistory`.
Times are timezone-aware ISO strings. Identifiers are opaque strings.

`snapshot` contains `id`, `collectedAt`, and these arrays:

- `controllers`: `{id, name, host, port, scope, identityKnown, coverage,
  failedCommands}`. Coverage: `completed|partial|failed|unknown`. The default
  scope is `effective`. Unknown legacy identity is never an automatic match.
- `roles`: `{id, controllerId, name, ssids:[], roleTypes:[], aclOrder:[],
  bindingRaw:[], contextComplete, observedUsers}`.
- `rules`: `{id, controllerId, roleId, acl, sequence, ordinal, raw, source,
  destination, service, action, sourceInterpretation, destinationInterpretation}`.
  Sequence is a display string; ordinal is a positive integer. IDs identify an
  occurrence in this snapshot, not a cross-snapshot matching promise.
- `aliases`: `{id, controllerId, name, entries:[{type,value,raw}]}`.
- `localNetworks`: `{controllerId, roleId, network, subnetMask, status, notes}`;
  empty unless explicitly included by the existing export option.
- `issues`: `{controllerId, roleId, message}` (roleId may be empty).

`annotations = {roles:{[roleId]:record}, rules:{[ruleId]:record}}`.
A record is `{text, status, updatedAt, confirmedAt, reasons:[], source}`.
Status: `unreviewed|reviewed|reused|needs_review`. `source` is null or
`{projectId,snapshotId,recordId,confirmedAt}`. Empty text is valid and preserved.

`changes`: array of `{type,controllerId,roleId,ruleId,message,previousRaw}`;
IDs may be empty for missing entities. `unresolvedAnnotations`: array of
`{id,kind,controllerId,controllerName,roleName,acl,raw,annotation,reason,
candidateIds:[],sourceProjectId,sourceSnapshotId}`. Kind is `role|rule`.
`importHistory`: `{projectId,snapshotId,importedAt,reused,needsReview,unresolved}`.

Browser namespace `AnnotationCore` (also CommonJS) provides:

- `parseProject(text)` / `validateProject(value)` -> safe validated copy, throw
  on unsupported versions, invalid references/types, unsafe keys or size limits.
- `reconcileProjects(current, previous, options={now,controllerMap})` ->
  `{project,summary:{reused,needsReview,unresolved}}`. Mapping is an explicit
  user-selected old-controller-ID to current-controller-ID association. Existing
  current notes are preserved; conflicts become unresolved records.
- `buildExportModel(project, {type:'all'|'selected'|'review',roleIds:[]}, now?)`
  -> `{projectId,snapshotId,revision,collectedAt,updatedAt,exportedAt,scopeLabel,
  controllers,roles,rules,aliases,localNetworks,changes,unresolvedAnnotations,
  issues,summary}`. Export role/rule objects contain `controllerName`, rules also
  `roleName`, and both contain `annotation` (a default empty record if absent).
  Summary contains `controllerCount,roleCount,ruleCount,annotatedRuleCount,
  needsReviewCount`. No DOM-dependent scope calculation.

`AnnotationExport` (also CommonJS) provides `createWorkbook(model, ExcelJS)`
(Workbook), `workbookBytes(model, ExcelJS)` (Promise<Uint8Array>), and
`printHtml(model)` (complete inert HTML string). The editor owns downloads and
print-window lifecycle. ExcelJS is bundled locally, with its license.

Python `annotation_project.build_annotation_project(frames, *,
parsed_controllers=None, collection_results=None, collected_at=None)` returns
the same DTO. Missing controller metadata is explicitly unknown. Only
allowlisted policy content enters the project.
