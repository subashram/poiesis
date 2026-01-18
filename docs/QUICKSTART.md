# Quick Start Guide

Get up and running in 5 minutes.

## Setup

```bash
cd /path/to/agent-workflow
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your-key-here
```

## The Key Insight

**Domain knowledge comes from YOUR design docs, not hardcoded agents.**

The Developer Agent adapts to any domain based on context you provide.

## Your First Workflow

### 1. Create a Design Document

```bash
cat > design/my-architecture.md << 'EOF'
# My System Architecture

## Technology Stack
- Python 3.11+ with type hints
- FastAPI for REST APIs
- PostgreSQL with SQLAlchemy
- Pydantic for validation

## Domain Model
- User: id, email, name, created_at
- Item: id, user_id, title, status

## API Patterns
- REST with JSON responses
- Pagination via cursor
- Errors: { "error": "CODE", "message": "..." }
EOF
```

### 2. Generate Contracts

```bash
python cli.py contracts "CRUD operations for users and items" -o crud-contracts.md
```

### 3. Plan Implementation

```bash
python cli.py plan "Implement user and item CRUD APIs" -o crud-tasks.yaml
```

### 4. Validate

```bash
python cli.py validate
```

### 5. Execute

```bash
python cli.py run-next
```

### 6. Review and Approve

```bash
python cli.py review
# Look at the file, then:
python cli.py approve <task-id>
```

### 7. Repeat

```bash
python cli.py run-next
```

---

## Essential Commands

| Command | What It Does |
|---------|--------------|
| `status` | Show overview |
| `list` | Show all tasks |
| `run-next` | Run next task |
| `review` | Show pending approvals |
| `approve <id>` | Approve a task |
| `reject <id> -r "..."` | Reject with feedback |
| `redteam <id>` | Security analysis |

---

## The Full Flow

```bash
# 1. Define your domain (the key step!)
vim design/my-architecture.md

# 2. Generate contracts
python cli.py contracts "My feature" -o feature-contracts.md

# 3. Plan implementation
python cli.py plan "Build my feature" -o feature-tasks.yaml

# 4. Validate
python cli.py validate

# 5. Run all tasks
python cli.py run-all

# 6. Review pending
python cli.py review

# 7. Red team security-critical tasks
python cli.py redteam <task-id>

# 8. Approve each
python cli.py approve <task-id>
```

---

## Example: Different Domains, Same Workflow

### IAM System

```
design/iam-architecture.md  →  RBAC, JWT, multi-tenancy
contracts/auth-contracts.md →  Token interfaces
tasks/iam-*.yaml           →  agent_type: developer
```

### ML Pipeline

```
design/ml-architecture.md   →  Training, inference, models
contracts/ml-contracts.md   →  Pipeline interfaces  
tasks/ml-*.yaml            →  agent_type: developer
```

### E-Commerce

```
design/ecommerce.md         →  Products, orders, payments
contracts/cart-contracts.md →  Shopping cart interfaces
tasks/ecommerce-*.yaml     →  agent_type: developer
```

**Same `developer` agent handles all of them!**

---

## Next Steps

- Read [README.md](../README.md) for full documentation
- Read [docs/AGENTS.md](AGENTS.md) for agent details
- Read [docs/WORKFLOW.md](WORKFLOW.md) for patterns
