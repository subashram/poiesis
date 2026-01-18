# Agent Reference Guide

This document provides detailed information about each agent in the workflow engine.

## Core Principle

> **Specialization comes from CONTEXT, not hardcoded agents.**

The Developer Agent adapts to any domain based on design documents and contracts you provide. You don't need different agents for different domains.

---

## Agent Overview

| Agent | Type | Purpose | Temperature |
|-------|------|---------|-------------|
| **Developer** | `developer` | Implement any domain (adapts to context) | 0.7 |
| **Contract** | `contract` | Define interfaces before implementation | 0.4 |
| **Planner** | `planner` | Decompose goals into atomic tasks | 0.5 |
| **Reviewer** | `reviewer` | Quality assurance with 3-pass reflection | 0.3 |
| **Red Team** | `redteam` | Adversarial security analysis | 0.6 |
| **Tester** | `tester` | Generate test cases | 0.5 |

---

## 🔧 Developer Agent (Primary)

**File:** `config/developer-agent.yaml`

### Purpose

The main implementation agent. Unlike traditional specialist agents, it adapts to **any domain** based on the design context you provide.

### How It Works

1. **Reads design documents** — Your architecture, patterns, tech stack
2. **Follows contracts** — Input/output specifications
3. **Writes code** — Clean, documented, production-quality
4. **Handles edge cases** — Security, errors, validation

### Why Generic Works

| Specialist Approach | Context-Driven Approach |
|---------------------|------------------------|
| `iam-agent.yaml` knows IAM | `developer-agent.yaml` + `design/iam-architecture.md` |
| `ml-agent.yaml` knows ML | `developer-agent.yaml` + `design/ml-architecture.md` |
| Need new agent per domain | Same agent, different context |

### What to Put in Design Docs

The Developer Agent looks for:

```markdown
# design/my-architecture.md

## Technology Stack
- Language: Python 3.11+
- Framework: FastAPI
- Database: PostgreSQL

## Domain Model
- Entity relationships
- Constraints and rules

## Patterns
- API conventions
- Error handling
- Authentication approach

## Key Decisions
- Why X over Y
- Tradeoffs accepted
```

### Output Format

```markdown
## Approach
Brief explanation of implementation decisions.

## Implementation
[Code with inline comments]

## Usage Example
[How to use the code]

## Dependencies
[Required libraries]

## Notes
[Assumptions, limitations, gotchas]
```

### When to Use

**Use `developer` for:**
- All implementation tasks
- Any domain (IAM, ML, infrastructure, frontend, etc.)
- Code generation
- System design

**The key:** Invest in your design documents, not in creating new agents.

---

## 📜 Contract Agent

**File:** `config/contract-agent.yaml`

### Purpose

Defines precise input/output contracts BEFORE implementation. This prevents context collapse and ensures consistent interfaces.

### When to Use

```bash
python cli.py contracts "User authentication with JWT and refresh tokens"
```

### What It Produces

```yaml
component: TokenService

input_contract:
  description: What this component receives
  types: |
    class LoginRequest:
        email: str
        password: str
  validation:
    - email must be valid format
    - password minimum 8 characters
  examples:
    - valid: { email: "user@example.com", password: "secret123" }
    - invalid: { email: "bad", password: "x" }

output_contract:
  description: What this component produces
  types: |
    class TokenPair:
        access_token: str
        refresh_token: str
        expires_in: int
  guarantees:
    - access_token expires in 15 minutes
    - refresh_token expires in 7 days

error_contract:
  errors:
    - name: InvalidCredentials
      when: Email/password don't match
      contains: Generic error message (no detail)
    - name: AccountLocked
      when: Too many failed attempts
      contains: Lockout duration
```

### Reflection Process

1. **Draft** — Identify boundaries, define types
2. **Validate** — Can every input be validated? Every output verified?
3. **Minimize** — Remove anything not strictly necessary

---

## 📊 Planner Agent

**File:** `config/planner-agent.yaml`

### Purpose

Decomposes high-level goals into atomic, contract-driven tasks.

### When to Use

```bash
python cli.py plan "Build user registration with email verification"
```

### Decomposition Principles

| Principle | Description |
|-----------|-------------|
| **Atomic** | Each task completable in ONE agent call |
| **Explicit** | Every task has input/output contracts |
| **Shallow** | Maximum 3 dependencies per task |
| **Parallel** | Prefer wide over deep task graphs |

### What It Produces

```yaml
tasks:
  - id: feature-001-contracts
    title: Define registration contracts
    agent_type: contract
    task_type: contract
    
  - id: feature-002-models
    title: Implement user models
    agent_type: developer
    task_type: implementation
    depends_on: [feature-001-contracts]
    
  - id: feature-003-service
    title: Implement registration service
    agent_type: developer
    task_type: implementation
    depends_on: [feature-002-models]
```

### Task Ordering

1. **Contract tasks first** — Define interfaces
2. **Implementation tasks** — Depend on contracts
3. **Test tasks** — Depend on implementations

---

## ✅ Reviewer Agent

**File:** `config/reviewer-agent.yaml`

### Purpose

Senior code reviewer with **3-pass reflection** to catch issues other reviewers miss.

### 3-Pass Process

```
┌─────────────────────────────────────────────────────────────┐
│  PASS 1: Initial Review                                      │
│  - Read thoroughly                                           │
│  - Note all issues                                           │
│  - Draft feedback                                            │
├─────────────────────────────────────────────────────────────┤
│  PASS 2: Challenge Critique                                  │
│  - "Am I being too harsh? Too lenient?"                      │
│  - "Did I miss anything important?"                          │
│  - "Are criticisms actionable?"                              │
├─────────────────────────────────────────────────────────────┤
│  PASS 3: Final Validation                                    │
│  - Re-read requirements                                      │
│  - "Would a senior engineer agree?"                          │
│  - Finalize score                                            │
└─────────────────────────────────────────────────────────────┘
```

### Review Criteria

| Category | Priority | Focus |
|----------|----------|-------|
| Security | Critical | Auth, input validation, secrets, errors |
| Architecture | High | Separation of concerns, abstractions |
| Code Quality | Medium | Naming, docs, types, edge cases |
| Maintainability | Medium | Readability, consistency |

### Scoring

| Score | Meaning |
|-------|---------|
| 0.9-1.0 | Excellent — Production ready |
| 0.7-0.8 | Good — Minor improvements |
| 0.5-0.6 | Acceptable — Some issues |
| 0.3-0.4 | Needs work — Significant issues |
| 0.0-0.2 | Not acceptable — Major problems |

**Pass threshold:** `score >= 0.7` AND no critical security issues

---

## 🔴 Red Team Agent

**File:** `config/redteam-agent.yaml`

### Purpose

Adversarial thinker that finds what could go wrong in production.

### Mindset

> "Assume everything will be attacked. Assume everything will fail."

### Attack Vectors

| Category | Examples |
|----------|----------|
| **Security** | Auth bypass, injection, privilege escalation |
| **Input** | Boundary values, type confusion, size attacks |
| **Concurrency** | Race conditions, deadlocks, resource exhaustion |
| **Business Logic** | State manipulation, replay attacks |
| **Failure Modes** | Network failures, data corruption |

### When to Use

```bash
# Manually
python cli.py redteam my-task-id

# Automatically (in task definition)
requires_redteam: true
```

### Output Format

```markdown
## 🔴 CRITICAL VULNERABILITIES
- Attack, Impact, Evidence, Fix

## 🟠 HIGH RISK ISSUES

## 🟡 MEDIUM RISK ISSUES

## 🔵 LOW RISK / HARDENING

## 💀 FAILURE SCENARIOS
- Trigger, Behavior, Impact, Recovery

## 📋 NEGATIVE TEST CASES
| Test | Input | Expected | Why |
```

---

## Creating Custom Specialists (Optional)

In most cases, the generic Developer Agent is sufficient. But if needed:

### 1. Copy the Template

```bash
cp config/specialist-template.yaml config/my-domain-agent.yaml
```

### 2. Customize

```yaml
name: My Domain Specialist
agent_type: mydomain  # Unique identifier
model: claude-sonnet-4-20250514
temperature: 0.7

system_prompt: |
  You are an expert in [DOMAIN]...
  
  ## Your Expertise
  - Area 1
  - Area 2
  
  ## Technology Stack
  ...
  
  ## Domain-Specific Principles
  ...
```

### 3. Use in Tasks

```yaml
agent_type: mydomain
```

### When to Create Specialists

| Do Create | Don't Create |
|-----------|--------------|
| Domain requires deep, specific expertise | You just want different tech stacks |
| Standard patterns don't apply | Design docs can express the domain |
| Compliance/regulatory requirements | Convenience or habit |

### Example Specialists

See `config/examples/` for:
- `iam-specialist.yaml` — Identity and Access Management

---

## Temperature Guide

| Temperature | Use For | Agents |
|-------------|---------|--------|
| 0.3 | Precise, consistent output | Reviewer |
| 0.4-0.5 | Structured, logical tasks | Contract, Planner |
| 0.6 | Adversarial thinking | Red Team |
| 0.7 | Creative implementation | Developer |
| 0.9 | Brainstorming | (not used by default) |

---

## Agent Selection Flow

```
┌─────────────────────────────────────────────────────────────┐
│  What are you doing?                                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Defining interfaces?                                        │
│    └── contract agent                                        │
│                                                              │
│  Breaking down a goal?                                       │
│    └── planner agent                                         │
│                                                              │
│  Building something?                                         │
│    └── developer agent (with domain in design docs)          │
│                                                              │
│  Checking quality?                                           │
│    └── reviewer agent (automatic)                            │
│                                                              │
│  Finding vulnerabilities?                                    │
│    └── redteam agent                                         │
│                                                              │
│  Need deep domain expertise?                                 │
│    └── Create specialist (see template)                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```
