---
document_type: policy
department: IT Operations
version: "1.0"
access_level: standard
---

# IT Service Management Policy

## Risk Classification for Actions

- **Low risk**: read-only checks, informational lookups, restarting a
  user-facing client application.
- **Medium risk**: resetting a single user's MFA/password, creating or
  updating a ticket, whitelisting a single confirmed-benign file hash.
- **High risk**: any production configuration change, account
  suspension or deletion, firewall/network rule changes, bulk actions
  affecting more than one user, or any action affecting a system with
  "critical" designation.

## Approval Requirements

All high-risk actions require explicit human approval before execution,
regardless of the confidence of any automated diagnosis. Medium-risk
actions require human approval when the diagnosis confidence is below
the organization's configured threshold.

## Ticket Lifecycle

Tickets progress through: open → in_progress → (pending_approval, if a
high-risk action is proposed) → resolved → closed. A ticket may be
reopened if the issue recurs within 7 days of resolution.

## Data Handling

Incident and ticket data may include personal information (names,
emails, device details) and must only be surfaced to users with
appropriate access level. Documents and query results must be filtered
by the requesting user's access level before being returned.
