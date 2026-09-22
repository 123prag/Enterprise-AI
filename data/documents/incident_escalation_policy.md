---
document_type: policy
department: IT Operations
version: "1.0"
access_level: standard
---

# Incident Escalation Policy

## Severity Definitions

- **Low**: Single user, minor inconvenience, workaround available.
- **Medium**: Single user or small group, no workaround, or minor
  productivity impact.
- **High**: Multiple users or a department affected, or a core system
  significantly degraded.
- **Critical**: Organization-wide outage, security breach, or complete
  loss of a critical business system.

## Escalation Triggers

An incident must be escalated to Tier 2 / relevant specialist team when:

1. It matches a "known problematic" software version pairing documented
   in the Windows Update Compatibility Guide or VPN Error Code Reference.
2. Three or more incidents in the same category occur within a 48-hour
   window (cluster detection).
3. Any system_status entry shows "degraded" or "outage" for a service
   relevant to the incident.
4. Severity is assessed as High or Critical.
5. The proposed remediation involves a production configuration change,
   account suspension, or any other action defined as high-risk in the
   IT Service Management Policy.

## Human-in-the-Loop Requirement

Any AI-assisted or automated remediation recommendation classified as
medium risk or higher must be routed to a human reviewer for approval
before execution. Low-risk, well-documented remediation steps (e.g.
"restart the VPN client") may be surfaced directly to the end user as a
suggestion without requiring approval.
