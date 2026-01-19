# Poiesis

*Greek: "the activity of bringing something into being"*

A lightweight, **domain-agnostic** workflow engine for orchestrating AI agents with human-in-the-loop review, contract-driven development, automated iteration, and adversarial testing.

## Philosophy

> **Specialization comes from CONTEXT, not hardcoded agents.**

The engine uses a single generic Developer Agent that adapts to any domain based on:
- **Design documents** — Define your architecture, patterns, technology stack
- **Contracts** — Define interfaces between components
- **Task prompts** — Define specific requirements

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       POIESIS                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📜 CONTRACT AGENT       Define interfaces BEFORE building  │
│         ↓                                                   │
│  📊 PLANNER AGENT        Decompose goals into atomic tasks  │
│         ↓                                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              🔄 FEEDBACK LOOP                       │    │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────┐   │    │
│  │  │DEVELOPER│─►│REVIEWER │─►│RED TEAM │─►│  QA   │   │    │
│  │  └─────────┘  └─────────┘  └─────────┘  └───────┘   │    │
│  │       ▲                                     │       │    │
│  │       └─────── Feedback if not pass ────────┘       │    │
│  └─────────────────────────────────────────────────────┘    │
│         ↓ All pass                                          │
│  👤 YOU                   Final approval                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Domain-Agnostic** | One generic developer agent adapts to any domain |
| **Contract-First** | Define interfaces before implementation |
| **Feedback Loop** | Automated iteration before human review |
| **3-Pass Review** | Reviewer reflects on its own critique |
| **QA Verification** | Verify contracts and acceptance criteria |
| **Adversarial Testing** | Red team finds security flaws |
| **Human-in-the-Loop** | You approve everything that matters |

## Quick Start

```bash
# Setup
cd /path/to/poiesis
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your-key-here

# 1. Define your domain
vim design/my-architecture.md

# 2. Generate contracts
python cli.py contracts "My feature" -o feature-contracts.md

# 3. Plan implementation
python cli.py plan "Build my feature" -o feature-tasks.yaml

# 4. Execute (with automated feedback loop)
python cli.py run-next

# 5. Review and approve
python cli.py review
python cli.py approve <task-id>
```

---

## Provider Configuration

Poiesis supports multiple LLM providers: Anthropic (default) and any OpenAI-compatible API (OpenAI, Ollama, vLLM, Together, Groq, etc.).

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | Global provider: `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | - | Anthropic API key |
| `OPENAI_API_KEY` | - | OpenAI-compatible API key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible API |

### Using Different Providers

**Anthropic (default):**
```bash
export ANTHROPIC_API_KEY=your-anthropic-key
python cli.py run-next
```

**OpenAI:**
```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your-openai-key
python cli.py run-next
```

**Ollama (local):**
```bash
export LLM_PROVIDER=openai
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama  # Ollama doesn't require a real key
# Update model in agent config to e.g., "llama3.1:70b"
python cli.py run-next
```

### Per-Agent Provider Override

You can mix providers by setting `provider` and `api_base_url` in agent configs:

```yaml
# config/my-local-agent.yaml
name: local-developer
agent_type: developer
provider: openai
api_base_url: http://localhost:11434/v1
model: llama3.1:70b
system_prompt: |
  You are a developer...
```

### Provider Priority

1. Agent YAML config `provider` field (if set)
2. Environment variable `LLM_PROVIDER`
3. Default: `anthropic`

---

## The Feedback Loop

The feedback loop enables **automated iteration** before human review:

```
Iteration 1/3
├── Developer: Generate implementation
├── Reviewer: Score 0.55 ❌ (below 0.7)
├── QA: FAIL ❌
└── Compile feedback → Back to Developer

Iteration 2/3
├── Developer: Fix based on feedback
├── Reviewer: Score 0.85 ✓
├── QA: PASS ✓
└── ALL PASS → Human Review
```

### Enable for a Task

```yaml
id: my-task
agent_type: developer

loop:
  enabled: true
  max_iterations: 3
  require_reviewer: true
  require_qa: true
  require_redteam: true  # For security-critical code
  min_review_score: 0.7
  qa_must_pass: true
  redteam_max_critical: 0
```

See [docs/FEEDBACK_LOOP.md](docs/FEEDBACK_LOOP.md) for details.

---

## Agents

| Agent | Type | Purpose |
|-------|------|---------|
| **Developer** | `developer` | Build any domain (adapts to context) |
| **Contract** | `contract` | Define interfaces |
| **Planner** | `planner` | Decompose goals |
| **Reviewer** | `reviewer` | Quality review (3-pass) |
| **QA** | `qa` | Verify contracts and criteria |
| **Red Team** | `redteam` | Adversarial testing |

See [docs/AGENTS.md](docs/AGENTS.md) for details.

---

## Directory Structure

```
poiesis/
├── config/                      # Agent configurations
│   ├── developer-agent.yaml     # 🔧 Generic developer
│   ├── contract-agent.yaml      # 📜 Interface definition
│   ├── planner-agent.yaml       # 📊 Task decomposition
│   ├── reviewer-agent.yaml      # ✅ Code review
│   ├── qa-agent.yaml            # 🧪 Quality assurance
│   └── redteam-agent.yaml       # 🔴 Adversarial testing
│
├── design/                      # YOUR domain knowledge
├── contracts/                   # YOUR interfaces
├── tasks/                       # Task definitions
├── artifacts/                   # Generated outputs
├── review/                      # Pending review
├── qa/                          # QA reports
├── redteam/                     # Security reports
└── done/                        # Approved artifacts
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `status` | Show workflow status (includes loop info) |
| `list` | List tasks with loop progress |
| `show <task_id>` | Show task details + loop history |
| `validate` | Check for missing contracts |
| `contracts "<feature>"` | Generate contracts |
| `plan "<goal>"` | Decompose into tasks |
| `run <task_id>` | Run task (with loop if enabled) |
| `run-next` | Run next available task |
| `run-all` | Run until review needed |
| `qa <target>` | Run QA verification |
| `redteam <target>` | Run security analysis |
| `review` | Show pending reviews |
| `approve <task_id>` | Approve task |
| `reject <task_id> -r "..."` | Reject with feedback |

---

## Task Configuration

```yaml
id: my-task
title: My Task
agent_type: developer
task_type: implementation
depends_on: []

# Contracts (key to preventing context collapse)
input_contract: |
  What this task receives...

output_contract: |
  What this task must produce...

acceptance_criteria:
  - Criterion 1
  - Criterion 2

# Review settings
requires_review: true
requires_human_approval: true
requires_qa: true
requires_redteam: true

# Feedback loop (optional)
loop:
  enabled: true
  max_iterations: 3
  require_reviewer: true
  require_qa: true
  require_redteam: false
  min_review_score: 0.7

prompt: |
  Detailed instructions...
```

---

## When to Use the Feedback Loop

| Scenario | Loop? | Why |
|----------|-------|-----|
| Security-critical code | ✅ Yes | Worth multiple iterations |
| Complex algorithms | ✅ Yes | Catches edge cases |
| Well-defined contracts | ✅ Yes | Clear pass criteria |
| Simple CRUD | ❌ No | Usually passes first try |
| Exploratory work | ❌ No | Unclear criteria |

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | 5-minute getting started |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent reference |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Workflow patterns |
| [docs/FEEDBACK_LOOP.md](docs/FEEDBACK_LOOP.md) | Feedback loop guide |

---

## Philosophy

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   Domain knowledge → DOCUMENTS, not agents                  │
│                                                             │
│   Contracts → BOUNDARIES, not implementations               │
│                                                             │
│   Feedback loops → AUTOMATED iteration                      │
│                                                             │
│   Humans → FINAL approval, not micromanagement              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**The goal is 2-5x productivity, not full autonomy.**

---

## License

MIT
