# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Poiesis** (Greek: "bringing into being") — A Python-based AI agent orchestration framework that uses Claude to automate software development workflows. The core philosophy is **"specialization from context, not hardcoded agents"** — a single generic Developer Agent adapts to any domain based on design documents and contracts.

Key capabilities:
- Contract-driven development (interfaces before implementation)
- Automated feedback loops (Developer → Reviewer → QA → Red Team)
- Human-in-the-loop final approval
- Air-gapped friendly (no external embedding APIs)

## Commands

```bash
# Setup (Anthropic - default)
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your-key-here

# Setup (OpenAI-compatible API)
pip install -r requirements.txt
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your-key-here
export OPENAI_BASE_URL=http://localhost:11434/v1  # Optional, for Ollama/vLLM/etc.

# Core workflow
python cli.py status                    # Show workflow status
python cli.py contracts "description"   # Generate contracts for a feature
python cli.py plan "goal"               # Generate implementation tasks
python cli.py validate                  # Validate task dependencies
python cli.py run-next                  # Run next ready task
python cli.py run-all                   # Run all ready tasks
python cli.py run <task-id>             # Run specific task

# Review and approval
python cli.py review                    # Show pending reviews
python cli.py approve <task-id>         # Approve a task
python cli.py reject <task-id> -r "reason"

# Analysis
python cli.py redteam <task-id>         # Security analysis
python cli.py qa <task-id>              # QA verification
python cli.py list                      # List all tasks
python cli.py show <task-id>            # Show task details + loop history
python cli.py export-done               # Export approved artifacts
```

## Architecture

### Core Components

```
cli.py                 # CLI interface - parses commands, calls WorkflowEngine
src/engine.py          # WorkflowEngine - orchestrates agents, manages state, runs feedback loops
src/llm_client.py      # LLMClient - multi-provider LLM wrapper (Anthropic + OpenAI-compatible)
src/context_retriever.py # ContextRetriever - smart context loading (keyword + TF-IDF)
src/models.py          # Data models (Task, LoopConfig, LoopState, WorkflowState, AgentConfig)
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | Global provider: `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | - | Anthropic API key |
| `OPENAI_API_KEY` | - | OpenAI-compatible API key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible API |

### Agent Configuration

Agents are defined in `config/*.yaml` with system prompts, temperature, model settings, and optional provider overrides:

| Agent | File | Purpose |
|-------|------|---------|
| Developer | `developer-agent.yaml` | Implements any domain (context-driven) |
| Contract | `contract-agent.yaml` | Defines interfaces before implementation |
| Planner | `planner-agent.yaml` | Decomposes goals into atomic tasks |
| Reviewer | `reviewer-agent.yaml` | Code review with 3-pass reflection |
| QA | `qa-agent.yaml` | Verifies contracts & acceptance criteria |
| Red Team | `redteam-agent.yaml` | Adversarial security analysis |

### Workflow Pipeline

```
design/     →  contracts/  →  tasks/     →  Feedback Loop   →  Human Review
(markdown)     (markdown)     (yaml)        (automated)        (approve/reject)
```

### Feedback Loop Flow

When `loop.enabled: true` in a task:
```
Developer → Reviewer (score) → Red Team (critical count) → QA (pass/fail)
    ↑                                                          ↓
    └─────────────── Feedback (if criteria not met) ──────────┘
```

Pass criteria (configurable): review score ≥ 0.7, QA passes, critical issues ≤ threshold

### Directory Structure

| Directory | Purpose | Git Status |
|-----------|---------|------------|
| `design/` | Domain knowledge (markdown) | Tracked |
| `contracts/` | Interface definitions | Tracked |
| `tasks/` | Task definitions (yaml) | Tracked |
| `config/` | Agent configurations | Tracked |
| `done/` | Approved artifacts | Tracked |
| `artifacts/` | Latest outputs | Ignored |
| `review/` | Pending reviews | Ignored |
| `qa/`, `redteam/`, `exports/` | Temporary | Ignored |

### State Persistence

`workflow_state.json` stores task statuses, loop states, and artifacts. Git-ignored (local per developer).

## Task Configuration

Tasks in `tasks/*.yaml` follow this structure:

```yaml
id: unique-task-id
title: Human-readable title
agent_type: developer
task_type: implementation  # contract, test, documentation, planning

input_contract: |
  What this task receives...
output_contract: |
  What this task must produce...

acceptance_criteria:
  - Criterion 1
  - Criterion 2

depends_on: [other-task-id]
requires_review: true
requires_human_approval: true

loop:
  enabled: false
  max_iterations: 3
  require_reviewer: true
  require_qa: true
  require_redteam: false
  min_review_score: 0.7

prompt: |
  Detailed instructions...
```

## Context Retrieval

Two modes based on document size:
- **Small docs (<20KB):** Load all context directly
- **Large docs (>20KB):** Smart retrieval using keyword matching and TF-IDF scoring, chunked by markdown headers

## Key Extension Points

- **New agents:** Create `config/my-agent.yaml` following `specialist-template.yaml`
- **Domain knowledge:** Add markdown files to `design/`
- **Tasks:** Add YAML files to `tasks/`
- **Contracts:** Add markdown files to `contracts/`
- **Per-agent provider override:** Add `provider` and `api_base_url` fields to agent YAML configs:
  ```yaml
  provider: openai
  api_base_url: http://localhost:11434/v1  # for Ollama
  model: llama3.1:70b
  ```
