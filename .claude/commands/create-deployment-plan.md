# Create Deployment Plan

Create a comprehensive deployment transition plan with Podio ticket and GitHub issues for migrating applications to cloud infrastructure.

## Usage

```
/create-deployment-plan [project-name] [current-state] [target-platform]
```

## Parameters

- `project-name`: Name of the project/application being migrated
- `current-state`: Brief description of current deployment (e.g., "local Docker")
- `target-platform`: Target cloud platform (e.g., "GCP", "AWS", "Azure")

## What This Command Does

1. **Creates Main Podio Ticket** with:
   - Project overview and migration strategy
   - Current state analysis
   - Target architecture description
   - 4-phase migration approach
   - Success criteria definition

2. **Generates GitHub Issues** for:
   - **Infrastructure setup** (3-4 issues)
   - **Application containerization** (per application)
   - **Deployment pipeline** (3-4 issues)
   - **Validation and testing** (3-4 issues)

3. **Stores Strategy in Memory** for future reference

## Example

```
/create-deployment-plan IDEA-Helsinki "local Docker containers" GCP
```

This creates a complete deployment plan with:
- 1 main Podio tracking ticket
- 10-15 detailed GitHub implementation issues
- Comprehensive migration strategy
- Clear task dependencies and acceptance criteria

## Features

- **Leverages existing infrastructure patterns** from memory
- **Creates proper issue linking** between Podio and GitHub
- **Follows proven migration strategies** (4-phase approach)
- **Includes comprehensive validation** and testing plans
- **Generates operational documentation** requirements
- **Memory storage** for future reference and learning

## Prerequisites

- Podio access configured
- GitHub repository access
- Understanding of current application architecture
- Target cloud platform access/project

## Output

- Podio ticket ID with full project overview
- GitHub issue numbers for all technical tasks
- Links between all tracking items
- Complete deployment strategy documentation
