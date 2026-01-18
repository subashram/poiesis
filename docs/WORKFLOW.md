# Workflow Guide

This document describes recommended workflow patterns for different scenarios.

## The Standard Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    STANDARD WORKFLOW                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. DESIGN PHASE                                             │
│     └── Create/update design docs in design/                 │
│                                                              │
│  2. CONTRACT PHASE                                           │
│     └── python cli.py contracts "<feature>" -o contracts.md  │
│     └── Review and edit contracts                            │
│                                                              │
│  3. PLANNING PHASE                                           │
│     └── python cli.py plan "<goal>" -o tasks.yaml            │
│     └── Review generated tasks                               │
│     └── python cli.py validate                               │
│                                                              │
│  4. IMPLEMENTATION PHASE                                     │
│     └── python cli.py run-next (repeat)                      │
│     └── Review each artifact                                 │
│     └── Red team if needed                                   │
│     └── Approve or reject                                    │
│                                                              │
│  5. COMPLETION                                               │
│     └── All tasks in done/                                   │
│     └── Update design docs with learnings                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Workflow Patterns

### Pattern 1: Greenfield Feature

Starting a completely new feature from scratch.

```bash
# 1. Document the design
vim design/my-feature-architecture.md

# 2. Generate contracts
python cli.py contracts "My new feature with X, Y, Z capabilities" \
  -o my-feature-contracts.md

# 3. Review and edit contracts
vim contracts/my-feature-contracts.md

# 4. Generate implementation tasks
python cli.py plan "Implement my feature" -o my-feature-tasks.yaml

# 5. Review generated tasks
vim tasks/my-feature-tasks.yaml

# 6. Validate workflow
python cli.py validate

# 7. Execute
python cli.py run-all

# 8. Review and approve each task
python cli.py review
python cli.py approve <task-id>
```

### Pattern 2: Security-Critical Feature

For authentication, authorization, payments, or sensitive data handling.

```bash
# Same as Pattern 1, but ensure tasks have:
# requires_redteam: true

# After running each task:
python cli.py run <task-id>
python cli.py redteam <task-id> -o <task-id>-security.md

# Review BOTH the artifact AND the red team report
cat review/<task-id>.md
cat redteam/<task-id>-security.md

# Only approve if red team findings are acceptable
python cli.py approve <task-id>
```

### Pattern 3: Incremental Enhancement

Adding to an existing feature or module.

```bash
# 1. Review existing design docs and contracts
cat design/existing-module.md
cat contracts/existing-contracts.md

# 2. Define contracts for the enhancement
python cli.py contracts "Add password reset to auth module" \
  -o password-reset-contracts.md

# 3. Create tasks manually (or use planner)
vim tasks/password-reset-tasks.yaml

# 4. Ensure tasks depend on existing contracts
# depends_on: [existing-auth-contracts]

# 5. Execute
python cli.py run-next
```

### Pattern 4: Bug Fix

Fixing an issue in existing code.

```bash
# 1. Document the bug
vim design/bugfix-description.md

# 2. Create a targeted task
cat > tasks/bugfix-001.yaml << EOF
id: bugfix-001
title: Fix race condition in token refresh
description: Addresses issue where concurrent refreshes cause token invalidation
agent_type: iam
task_type: implementation
requires_redteam: true

input_contract: |
  - Current refresh token implementation from done/auth-implementation.md
  - Bug description: Race condition when two requests refresh simultaneously

output_contract: |
  - Modified refresh_token() function with locking
  - Must handle concurrent requests safely
  - No token invalidation for legitimate requests

acceptance_criteria:
  - Concurrent refresh requests don't invalidate tokens
  - Single request still works normally
  - No deadlocks introduced

prompt: |
  Fix the race condition in the token refresh implementation...
EOF

# 3. Run with red team
python cli.py run bugfix-001
python cli.py redteam bugfix-001
python cli.py approve bugfix-001
```

### Pattern 5: Rapid Prototyping

Quick exploration without full process.

```bash
# Skip contracts for speed (not recommended for production)
python cli.py run <task-id>

# WARNING will appear:
# ⚠️  WARNING: Implementation task has no contracts defined.

# Useful for:
# - Proof of concepts
# - Exploring approaches
# - Learning/experimentation

# NOT for:
# - Production code
# - Security-sensitive features
# - Code that will be maintained
```

---

## Task Lifecycle

```
                    ┌─────────┐
                    │ PENDING │
                    └────┬────┘
                         │ python cli.py run <id>
                         ▼
                    ┌─────────┐
                    │ RUNNING │
                    └────┬────┘
                         │ Generation complete
                         ▼
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
    requires_human_approval    auto-approve
              │                     │
              ▼                     │
         ┌────────┐                 │
         │ REVIEW │                 │
         └────┬───┘                 │
              │                     │
      ┌───────┼───────┐             │
      │       │       │             │
      ▼       │       ▼             │
┌──────────┐  │  ┌──────────┐       │
│ APPROVED │  │  │ REJECTED │       │
└────┬─────┘  │  └─────┬────┘       │
     │        │        │            │
     │        │        │ (edit task, retry)
     │        │        ▼            │
     │        │   ┌─────────┐       │
     │        │   │ PENDING │       │
     │        │   └─────────┘       │
     │        │                     │
     ▼        ▼                     ▼
         ┌───────────┐
         │ COMPLETED │
         └───────────┘
```

---

## Handling Failures

### Task Generation Failed

```bash
$ python cli.py run my-task
Error generating artifact: API error

# Check logs, retry
python cli.py run my-task
```

### Review Rejected

```bash
$ python cli.py reject my-task -r "Missing error handling"

# Task returns to PENDING
# Edit the task prompt if needed
vim tasks/my-task.yaml

# Re-run
python cli.py run my-task
```

### Red Team Found Critical Issues

```bash
# Option 1: Fix and re-run
python cli.py reject my-task -r "Critical: SQL injection in line 42"
# Edit task prompt to address issue
python cli.py run my-task

# Option 2: Accept risk (document why)
# Add comment to task or approval
python cli.py approve my-task
# Document in design/ why risk was accepted
```

### Circular Dependencies

```bash
$ python cli.py validate
❌ task-a: Circular dependency detected

# Fix: Edit task definitions to break the cycle
vim tasks/task-a.yaml
vim tasks/task-b.yaml
```

---

## Multi-Developer Workflow

When multiple people work on the same workflow:

### Git Integration

```bash
# Structure for version control
agent-workflow/
├── .gitignore          # Ignore artifacts/, review/
├── config/             # Shared agent configs
├── design/             # Shared design docs
├── contracts/          # Shared contracts
├── tasks/              # Shared task definitions
├── done/               # Approved artifacts (commit these)
└── workflow_state.json # Don't commit (local state)
```

**.gitignore:**
```
artifacts/
review/
redteam/
workflow_state.json
__pycache__/
```

### Branching Strategy

```
main
 │
 ├── feature/auth-module
 │   ├── design/auth-architecture.md
 │   ├── contracts/auth-contracts.md
 │   └── tasks/auth-*.yaml
 │
 └── feature/billing-module
     ├── design/billing-architecture.md
     └── ...
```

### Merge Process

1. Feature branch runs workflow
2. Artifacts approved → committed to done/
3. PR includes done/ artifacts + design docs
4. Code review by humans
5. Merge to main

---

## Optimization Tips

### Reduce API Calls

```yaml
# Batch related work into single tasks
id: user-crud-all
prompt: |
  Implement all CRUD operations for User:
  - create_user()
  - get_user()
  - update_user()
  - delete_user()
```

### Skip Review for Low-Risk Tasks

```yaml
requires_review: false          # Skip automated review
requires_human_approval: false  # Auto-approve
```

### Parallel Execution

Design tasks to minimize dependencies:

```
BETTER (parallel):
task-a ──┐
task-b ──┼──► task-d
task-c ──┘

WORSE (serial):
task-a ──► task-b ──► task-c ──► task-d
```

### Reuse Contracts

```yaml
# Multiple tasks can reference same contract
contract_task: shared-auth-contracts
```

---

## Troubleshooting

### "No tasks ready to run"

```bash
python cli.py status
# Check: Are tasks stuck in review?
python cli.py review

# Or: Are dependencies not met?
python cli.py list
```

### "No agent configured for type"

```bash
# Check agent type matches config file
ls config/
cat config/iam-agent.yaml | grep agent_type

# Ensure type is in AgentType enum
grep -A 10 "class AgentType" src/models.py
```

### "Context too large"

- Split design docs into smaller files
- Remove completed contracts that are no longer needed
- Use more specific task prompts

### "Inconsistent outputs"

- Lower temperature in agent config
- Add more specific constraints to prompt
- Add acceptance criteria
- Use contracts to define exact expectations
