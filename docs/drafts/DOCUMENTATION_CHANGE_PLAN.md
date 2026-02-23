# Documentation Change Plan

This file is a temporary execution checklist for refurbishing Orchard UI docs.  
Remove this file after documentation work is complete and validated.

## Section 1 - Restructure and Archive

- [x] Create `docs/drafts/`
- [x] Move old root `README.md` to `docs/drafts/README_old.md`
- [x] Move old markdown files from `docs/` into `docs/drafts/`
- [x] Create new structure:
  - [x] `docs/getting-started/`
  - [x] `docs/administration/`
  - [x] `docs/user-guide/`
  - [x] `docs/architecture/`
  - [x] `docs/development/`

## Section 2 - Root and Entry Docs

- [x] Write new root `README.md`
- [x] Add `docs/CHANGELOG.md`
- [x] Add `docs/troubleshooting.md`

## Section 3 - Getting Started Docs

- [x] `docs/getting-started/prerequisites.md`
- [x] `docs/getting-started/installation.md`
- [x] `docs/getting-started/quick-start.md`

## Section 4 - Administration Manual

- [x] `docs/administration/node-setup.md`
- [x] `docs/administration/registry-setup.md`
- [x] `docs/administration/reverse-proxy.md`
- [x] `docs/administration/user-management.md`
- [x] `docs/administration/registry-storage.md`
- [x] `docs/administration/deployment.md`
- [x] `docs/administration/backup-and-recovery.md`

## Section 5 - User Manual

- [x] `docs/user-guide/dashboard.md`
- [x] `docs/user-guide/vm-lifecycle.md`
- [x] `docs/user-guide/vnc-console.md`

## Section 6 - Architecture Docs

- [x] `docs/architecture/overview.md`
- [x] `docs/architecture/data-model.md`
- [x] `docs/architecture/vnc-architecture.md`
- [x] `docs/architecture/registry-and-cleanup.md`

## Section 7 - Developer Docs

- [x] `docs/development/setup.md`
- [x] `docs/development/project-structure.md`
- [x] `docs/development/api-reference.md`
- [x] `docs/development/configuration-reference.md`

## Section 8 - Quality Gate

- [x] Confirm all old markdown content is preserved under `docs/drafts/`
- [x] Verify cross-links between new docs
- [x] Verify install/admin paths are complete and runnable
- [x] Verify route and config references match codebase
- [x] Final sweep for typos and naming consistency

## Suggested Parallelization for Other Agents

### Agent A - User and Getting Started
- Own Section 3 and Section 5

### Agent B - Administration
- Own Section 4

### Agent C - Architecture and Development
- Own Section 6 and Section 7

### Agent D - Validation
- Own Section 8 and final consistency pass
