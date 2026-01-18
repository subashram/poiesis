# IAM Module Architecture

## Overview

The IAM module provides identity and access management for a multi-tenant Cloud Management Platform (CMP).

## Core Principles

1. **Tenant Isolation** — Users can never access resources outside their tenant
2. **Least Privilege** — Default deny; explicit grants required
3. **Deny Overrides Allow** — If any policy denies, access is denied
4. **Audit Everything** — All access decisions are logged

## Domain Model

```
┌─────────────────────────────────────────────────────────────┐
│                         TENANT                               │
│  The root isolation boundary. All entities belong to one.   │
└─────────────────────────────────────────────────────────────┘
        │
        ├──────────────────────┬─────────────────────┐
        ▼                      ▼                     ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│    USER      │      │    ROLE      │      │   POLICY     │
│              │      │              │      │              │
│ - id         │      │ - id         │      │ - id         │
│ - email      │◄────▶│ - name       │      │ - effect     │
│ - tenant_id  │ M:N  │ - tenant_id  │      │ - actions[]  │
│ - status     │      │ - permissions│      │ - resources[]│
└──────────────┘      └──────────────┘      └──────────────┘
                              │
                              ▼
                      ┌──────────────┐
                      │ PERMISSION   │
                      │              │
                      │ - resource   │
                      │ - action     │
                      │ e.g. vm:create│
                      └──────────────┘
```

## Permission Format

Permissions follow the pattern: `resource:action`

| Resource | Actions |
|----------|---------|
| `vm` | `create`, `read`, `update`, `delete`, `start`, `stop` |
| `network` | `create`, `read`, `update`, `delete` |
| `storage` | `create`, `read`, `update`, `delete`, `mount` |
| `user` | `create`, `read`, `update`, `delete`, `invite` |
| `role` | `create`, `read`, `update`, `delete`, `assign` |
| `*` | Wildcard (matches any resource) |

Action wildcards: `vm:*` means all actions on VMs.

## API Contracts

### Authentication

```
POST /auth/login
  Request:  { email: string, password: string }
  Response: { access_token: string, refresh_token: string, expires_in: int }

POST /auth/refresh
  Request:  { refresh_token: string }
  Response: { access_token: string, expires_in: int }

POST /auth/logout
  Request:  { refresh_token: string }
  Response: { success: boolean }
```

### JWT Payload

```json
{
  "sub": "user-uuid",
  "tenant_id": "tenant-uuid",
  "email": "user@example.com",
  "roles": ["admin", "developer"],
  "permissions": ["vm:*", "network:read"],
  "exp": 1699999999,
  "iat": 1699999000
}
```

### Authorization Check

```
POST /authorize
  Request:  { user_id: string, action: string, resource: string }
  Response: { allowed: boolean, reason?: string }
```

## Key Decisions (ADRs)

### ADR-001: RBAC over ABAC
**Decision:** Use Role-Based Access Control as primary model.
**Rationale:** Simpler to understand, audit, and manage. ABAC can be added later for fine-grained policies.

### ADR-002: Tenant ID in JWT
**Decision:** Include tenant_id in JWT payload.
**Rationale:** Every API call needs tenant context. Embedding it avoids database lookups.

### ADR-003: Permission Caching
**Decision:** Cache resolved permissions in Redis with 5-minute TTL.
**Rationale:** Permission resolution involves role hierarchy traversal. Cache avoids repeated computation.

### ADR-004: Deny Takes Precedence
**Decision:** If any policy denies access, the request is denied regardless of allows.
**Rationale:** Security principle — explicit denies are intentional restrictions.

## Glossary

| Term | Definition |
|------|------------|
| **Tenant** | An isolated customer/organization boundary |
| **Principal** | An entity (user or service) that can perform actions |
| **Resource** | Something that can be acted upon (VM, network, etc.) |
| **Action** | An operation on a resource (create, read, delete) |
| **Permission** | A `resource:action` pair |
| **Role** | A named collection of permissions |
| **Policy** | A rule that allows or denies specific actions |

## Integration Points

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   API GW    │────▶│   IAM       │────▶│  Services   │
│             │     │   Module    │     │  (VM, Net)  │
└─────────────┘     └─────────────┘     └─────────────┘
      │                   │                    │
      │              ┌────┴────┐               │
      │              ▼         ▼               │
      │        ┌─────────┐ ┌─────────┐        │
      │        │ User DB │ │ Redis   │        │
      │        │         │ │ (cache) │        │
      │        └─────────┘ └─────────┘        │
      │                                        │
      └──────────── Audit Log ─────────────────┘
```

## Security Boundaries

1. **API Gateway** — Validates JWT signature, extracts tenant context
2. **IAM Module** — Evaluates permissions, makes allow/deny decisions
3. **Service Layer** — Enforces resource-level ownership checks
4. **Database** — Row-level security filtered by tenant_id
