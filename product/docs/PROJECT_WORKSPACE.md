# Project workspace

## What works

The backend and mobile client now provide a private, account-scoped project workspace for text and source files. Content is stored in the application's SQL database; the API never joins a user-supplied path to the host filesystem and never runs project content as code.

- Create/list/delete projects.
- List, create, read, replace, and delete files in a project.
- Use optimistic revision checks on replacements so stale clients cannot silently overwrite a newer save.
- Save up to three recent project checkpoints and view bounded unified diffs against a checkpoint.
- Include project metadata, file contents, and checkpoints in the authenticated NDJSON account export.
- Let mobile sharing request a 500,000-byte cap; the server preflights the caller's export as a stream and rejects it with `413` before sending any NDJSON when it is too large. Uncapped authenticated exports remain streaming for full data retrieval.
- Delete files/checkpoints through project deletion and account deletion cascades.

The Android UI exposes project creation, browsing, a plain text/code editor, save, checkpoint, diff, and confirmed project/file deletion. It is English/Arabic-aware. The UI only calls these routes when `/health/ready` advertises `project_workspace`.

## API surface

All routes below require a valid bearer token. Projects are always selected through the authenticated account; another account's project is reported as not found.

| Method | Route | Behavior |
|---|---|---|
| `GET` | `/api/v1/projects` | List the caller's projects |
| `POST` | `/api/v1/projects` | Create a project (`name`, optional `description`) |
| `DELETE` | `/api/v1/projects/{project_id}` | Delete a project and all child content |
| `GET` | `/api/v1/projects/{project_id}/files` | List file paths, byte sizes, revisions and update times |
| `GET` | `/api/v1/projects/{project_id}/files/{path}` | Read one text file |
| `PUT` | `/api/v1/projects/{project_id}/files/{path}` | Create a file or revision-checked replacement |
| `DELETE` | `/api/v1/projects/{project_id}/files/{path}` | Delete a file |
| `POST` | `/api/v1/projects/{project_id}/checkpoints` | Capture a labeled file snapshot |
| `GET` | `/api/v1/projects/{project_id}/checkpoints` | List retained checkpoints |
| `GET` | `/api/v1/projects/{project_id}/diff?checkpoint_id=…` | Compare current files to one owned checkpoint |

When replacing an existing file, send its current `expected_revision`. The API returns `428` if this field is omitted and `409` if it is stale. A new file must not send an expected revision. OpenAPI at `/openapi.json` is the machine-readable contract.

## Security and resource limits

- Paths are logical POSIX-style names only; absolute paths, `..`, `.`, empty segments, backslashes, NUL/control bytes, excessive depth, and overly long names are rejected. No host filesystem path is constructed.
- Limit: 10 projects per account, 100 files per project, 512 KiB per UTF-8 file, 2 MiB current file content per project, and three retained checkpoints per project.
- Diff responses are capped at 256 KiB. A large diff is rejected rather than silently truncated.
- Project rows are locked when creating files/checkpoints or enforcing project-level limits on PostgreSQL. Writes use revisions to detect stale editors.
- Every route scopes data to the owner; project deletion and account deletion cascade through files and snapshots. Exports query through the project owner and exclude other accounts.
- Data remains ordinary user content: it is retained in the database until the user deletes the project/account, and is included in their export. Configure database encryption, backups, and retention at the hosting provider before Production use.

## Deliberate boundaries

This is a database-backed editor/checkpoint slice, **not** a host directory or full coding-agent environment. It currently has no shell/terminal, package installer, Git provider, language server, file version history beyond current revision/checkpoint diffs, checkpoint restore route, general uploads/downloadable artifacts, document parsing, or automated code execution. The API must not execute these files. A separately isolated execution provider and its credentials, policies, limits, and tests are still required.

## Verification

- API integration tests cover owner isolation, create/read/update/delete, revision conflict behavior, checkpoint diffs, export inclusion, account deletion cascade, path validation, project/file/storage quotas, rejection of over-limit mobile exports before download, and termination with checkpoint rows present.
- Fresh SQLite Alembic migration to head and `alembic check` pass. The current test suite exercises SQLite; PostgreSQL row-lock and JSON behavior have not been tested against a live PostgreSQL service.
- TypeScript check, Android Metro export, and a local debug-signed APK build pass. The APK signature/permissions were verified, but there was no emulator/physical-device interaction or deployment of these endpoints. The current hosted Preview does not yet advertise this capability; the mobile UI hides workspace operations there.
