# Feedback Loop (Rework Loop)

The feedback loop enables automated iteration between agents before human review, reducing back-and-forth with humans.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FEEDBACK LOOP                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │DEVELOPER │───►│ REVIEWER │───►│ RED TEAM │───►│    QA    │          │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘          │
│       ▲                                               │                  │
│       │                                               ▼                  │
│       │                                        ┌─────────────┐          │
│       │         Feedback + Issues              │ ALL PASS?   │          │
│       └────────────────────────────────────────│             │          │
│                      NO                        └──────┬──────┘          │
│                                                       │ YES             │
│                                                       ▼                  │
│                                                ┌─────────────┐          │
│                                                │   HUMAN     │          │
│                                                │   REVIEW    │          │
│                                                └─────────────┘          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## How It Works

1. **Developer generates** the initial implementation
2. **Reviewer checks** code quality and gives a score
3. **Red Team attacks** looking for vulnerabilities (if enabled)
4. **QA verifies** contracts and acceptance criteria (if enabled)
5. **Check pass criteria**:
   - Review score ≥ threshold?
   - QA passed?
   - No critical security issues?
6. **If all pass** → Send to human review
7. **If any fail** → Compile feedback, send back to Developer
8. **Repeat** until pass or max iterations reached

## Configuration

Add loop configuration to any task:

```yaml
id: my-task
agent_type: developer
# ... other fields ...

loop:
  enabled: true
  max_iterations: 3        # Max rework attempts
  require_reviewer: true   # Include reviewer in loop
  require_qa: true         # Include QA in loop
  require_redteam: false   # Include red team in loop (slower)
  
  # Pass thresholds
  min_review_score: 0.7    # Minimum reviewer score to pass
  qa_must_pass: true       # QA must return PASS
  redteam_max_critical: 0  # Max critical issues allowed
```

## Pass Criteria

| Check | Pass If |
|-------|---------|
| Reviewer | `score >= min_review_score` (default 0.7) |
| QA | Returns `PASS` (if `qa_must_pass: true`) |
| Red Team | Critical issues ≤ `redteam_max_critical` (default 0) |

All enabled checks must pass for the loop to complete.

## Loop Flow Example

```
Iteration 1/3
├── Developer: Generate implementation
├── Reviewer: Score 0.55 (below 0.7 threshold)
├── QA: FAIL (missing edge cases)
└── Result: NEEDS REWORK

Iteration 2/3
├── Developer: Fix based on feedback
├── Reviewer: Score 0.72 ✓
├── QA: NEEDS_WORK (partial fix)
└── Result: NEEDS REWORK

Iteration 3/3
├── Developer: Fix remaining issues
├── Reviewer: Score 0.85 ✓
├── QA: PASS ✓
└── Result: ALL PASS → Human Review
```

## CLI Commands

```bash
# Run a task with loop enabled
python cli.py run my-task

# Check status (shows loop iterations)
python cli.py status

# List tasks (shows loop progress)
python cli.py list

# Show task details (includes loop history)
python cli.py show my-task
```

## What Gets Passed to Developer

On rework iterations, the Developer receives:

1. **Original task prompt**
2. **Previous implementation** (the code that failed)
3. **Feedback from checks**:
   - Reviewer's issues and suggestions
   - QA's failed tests and edge cases
   - Red team's vulnerabilities

The Developer is instructed to fix ALL identified issues and produce a complete new implementation.

## When to Use Loops

### ✅ Good Candidates

- Security-critical code (auth, authorization)
- Complex algorithms with many edge cases
- Code that must meet strict contracts
- High-value tasks worth multiple iterations

### ❌ Not Recommended

- Simple tasks that rarely fail review
- Tasks where iteration adds little value
- Time-sensitive work
- Tasks with vague acceptance criteria

## Cost Considerations

Each loop iteration costs:
- 1 Developer call
- 1 Reviewer call (if enabled)
- 1 Red Team call (if enabled)
- 1 QA call (if enabled)

For a task with `max_iterations: 3` and all checks enabled:
- Best case: 4 API calls (pass first try)
- Worst case: 12 API calls (3 full iterations)

## Loop vs Manual Iteration

| Approach | When to Use |
|----------|-------------|
| **Loop enabled** | High-stakes, well-defined criteria |
| **Manual iteration** | Exploratory, unclear requirements |
| **No iteration** | Simple tasks, low risk |

## Example Task with Loop

```yaml
id: auth-service
title: JWT Authentication Service
agent_type: developer
task_type: implementation

loop:
  enabled: true
  max_iterations: 3
  require_reviewer: true
  require_qa: true
  require_redteam: true  # Security-critical!
  min_review_score: 0.8  # Higher bar for auth
  redteam_max_critical: 0

output_contract: |
  AuthService class with:
  - login(email, password) -> TokenPair
  - refresh(refresh_token) -> TokenPair
  - validate(access_token) -> User
  - logout(refresh_token) -> None

acceptance_criteria:
  - JWT tokens expire in 15 minutes
  - Refresh tokens rotate on use
  - Invalid tokens raise specific exceptions
  - All inputs are validated
  - No secrets in logs

prompt: |
  Implement a JWT authentication service...
```

## Monitoring Loops

The review file shows loop history:

```markdown
## 🔄 Feedback Loop Summary

- Iterations: 2
- Review scores: 0.55 → 0.85
- QA results: FAIL → PASS
- Red team critical: 1 → 0
```

## Best Practices

1. **Set realistic max_iterations** — Usually 2-3 is enough
2. **Use specific acceptance criteria** — Vague criteria = infinite loops
3. **Enable red team for security code** — Worth the extra cost
4. **Review loop history** — Understand what was fixed
5. **Don't over-rely on automation** — Human judgment still matters
