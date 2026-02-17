# Document Management & Detection

This project uses Blueprint development with automatic document detection. Claude will recognize opportunities to create formal documentation and suggest relevant skills.

## Document Types

### Product Requirements Documents (PRD)
- **Location**: `docs/prds/`
- **Trigger**: When discussing new features or requirements
- **Create with**: `/blueprint:derive-prd` or `/blueprint:prp-create`
- **Purpose**: Define what to build and why

### Architecture Decision Records (ADR)
- **Location**: `docs/adrs/`
- **Trigger**: When making significant architectural decisions or trade-offs
- **Create with**: `/blueprint:derive-adr`
- **Purpose**: Document decisions and their rationale for future reference

### Product Requirement Prompts (PRP)
- **Location**: `docs/prps/`
- **Trigger**: When detailed implementation guidance is needed
- **Create with**: `/blueprint:prp-create` or `/blueprint:prp-execute`
- **Purpose**: Detailed specs and implementation checklists for specific features

## When Documents Are Suggested

Claude will offer to create documents when:

1. **PRD Opportunity**: Discussing new features or system requirements
   - Example: "We need to add caching to improve performance"
   - Claude offers: `/blueprint:derive-prd` to formalize as a requirement

2. **ADR Opportunity**: Making architectural decisions or analyzing trade-offs
   - Example: "Should we use Redis or in-memory cache?"
   - Claude offers: `/blueprint:derive-adr` to document the decision

3. **PRP Opportunity**: Complex features needing detailed implementation guidance
   - Example: "How should we structure the new validation worker pool?"
   - Claude offers: `/blueprint:prp-create` for detailed specs

## Document Organization

```
docs/
├── blueprint/
│   ├── manifest.json            # Version tracking and configuration
│   ├── feature-tracker.json     # Feature progress tracking
│   ├── work-orders/             # Task packages for subagents
│   │   ├── completed/
│   │   └── archived/
│   └── ai_docs/                 # Curated documentation
├── prds/                        # Product Requirements Documents
├── adrs/                        # Architecture Decision Records
├── prps/                        # Product Requirement Prompts
└── (existing docs)
```

## Using Generated Documents

After creating a document:

1. **PRD**: Use to guide feature planning and requirements tracking
   - Link in `/blueprint:feature-tracker-sync` to track completion
   - Reference in GitHub issues for requirements context

2. **ADR**: Reference in code comments and pull request descriptions
   - Keep as historical record of decisions
   - Use for onboarding new team members

3. **PRP**: Use as detailed spec during implementation
   - Break into tasks for `/project:continue` workflow
   - Execute with `/blueprint:prp-execute` for step-by-step guidance

## Feature Tracking

IDEA-Helsinki has feature tracking enabled:
- **Source**: README.md
- **Track with**: `/blueprint:feature-tracker-sync` to extract requirements
- **View progress**: `/blueprint:feature-tracker-status`

Features extracted from the README are tracked in `docs/blueprint/feature-tracker.json`.

## Workflow Commands

Quick access to document creation and management:

```bash
# Create documents
/blueprint:derive-prd          # Create PRD from discussion
/blueprint:derive-adr          # Create ADR from analysis
/blueprint:prp-create          # Create detailed PRP
/blueprint:prp-execute         # Execute PRP implementation

# Manage documents
/blueprint:derive-plans        # Derive docs from git history
/blueprint:feature-tracker-sync # Sync features from requirements
/blueprint:status              # View configuration and status
/blueprint:sync                # Check for stale content
```

## Tips

- **Small, focused documents**: Create separate documents for different concerns (e.g., one ADR per decision)
- **Link documents**: Reference related PRDs/ADRs in document content
- **Version control**: Commit all documents to git (except `work-orders/` which may contain sensitive details)
- **Regular review**: Use `/blueprint:status` to stay informed about configuration and available workflows
