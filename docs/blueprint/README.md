# Blueprint Development for IDEA-Helsinki

This directory contains Blueprint development configuration and generated documentation for the IDEA-Helsinki project.

## Structure

- **`manifest.json`** - Blueprint configuration and version tracking (v3.1.0)
- **`feature-tracker.json`** - Feature progress tracking from README.md
- **`work-orders/`** - Task packages for subagents (task-specific, not committed)
  - `completed/` - Archived completed tasks
  - `archived/` - Archived work items
- **`ai_docs/`** - Curated documentation references
  - `libraries/` - Third-party library docs
  - `project/` - Project-specific documentation

## Configuration

Blueprint is configured in `.claude/rules/` with modular rules:
- `development.md` - Development workflow and TDD practices
- `testing.md` - Testing requirements and patterns
- `document-management.md` - Document organization and automatic detection

## Feature Tracking

Feature progress is tracked in `feature-tracker.json` with source from `README.md`:
- View progress: `/blueprint:feature-tracker-status`
- Sync with requirements: `/blueprint:feature-tracker-sync`

## Document Types

### Product Requirements Documents (PRD)
- Location: `docs/prds/`
- Create with: `/blueprint:derive-prd` or `/blueprint:prp-create`

### Architecture Decision Records (ADR)
- Location: `docs/adrs/`
- Create with: `/blueprint:derive-adr`

### Product Requirement Prompts (PRP)
- Location: `docs/prps/`
- Create with: `/blueprint:prp-create` or `/blueprint:prp-execute`

## Management Commands

```bash
/blueprint:status                 # View configuration and available commands
/blueprint:derive-prd             # Create PRD from discussion
/blueprint:derive-adr             # Create ADR from analysis
/blueprint:prp-create             # Create detailed PRP
/blueprint:prp-execute            # Execute PRP implementation
/blueprint:feature-tracker-sync   # Sync features from requirements
/blueprint:feature-tracker-status # View feature completion stats
/blueprint:sync                   # Check for stale content
/blueprint:upgrade                # Upgrade to latest format version
```

## See Also

- Main project instructions: `/Users/lgates/repos/ForumViriumHelsinki/IDEA-Helsinki/CLAUDE.md`
- Modular rules: `.claude/rules/`
