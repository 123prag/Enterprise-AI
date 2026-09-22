---
document_type: guide
department: IT Operations
version: "1.0"
access_level: standard
---

# Authentication Troubleshooting Guide

## Overview

Covers SSO login failures, account lockouts, and access-denied errors
against internal portals and applications.

## Common Issues

### Repeated Login Failures (AUTH-401)

1. Confirm the account is not locked due to too many failed attempts
   (5 failures triggers a 15-minute lockout).
2. Confirm the user is using their corporate email, not a personal alias.
3. Check the SSO Identity Provider system status — a degraded IdP causes
   cluster failures across many users simultaneously, which should be
   escalated rather than treated as individual tickets.

### Access Denied After Role Change (AUTH-403)

Role/permission changes can take up to 30 minutes to propagate through
the SSO connector cache. If a user reports access denial immediately
after a role change:

1. Confirm the role change was actually applied in the identity system.
2. Ask the user to log out completely and log back in (not just refresh).
3. If still denied after 30 minutes, escalate to Identity & Access team.

### Password Reset Email Never Received

See the Password Reset Procedure document. Common causes are spam
filtering and using an outdated recovery email.

## When to Escalate

- More than 5 users report login failures within the same 10-minute
  window — likely an SSO Identity Provider issue, not individual account
  issues.
- Any suspected compromised credential — escalate immediately per the
  Security Incident Response SOP, do not attempt remediation directly.
