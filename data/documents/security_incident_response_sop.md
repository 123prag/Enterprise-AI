---
document_type: sop
department: Security
version: "1.0"
access_level: standard
---

# Security Incident Response SOP

## Scope

Applies to any suspected active compromise, confirmed malware execution,
unauthorized access, or credential compromise. Does not apply to routine
EDR false positives (see Endpoint Security SOP).

## Immediate Actions

1. Do not attempt remediation through standard IT tooling.
2. Isolate the affected device from the network if compromise is
   suspected (this is a high-risk action requiring approval unless an
   active, confirmed breach justifies immediate isolation per the
   security team's standing authority).
3. Escalate to the Security team immediately with all available context:
   affected user, device, timeline, and observed indicators.
4. Preserve logs — do not restart or reimage the device before the
   security team has completed initial forensic collection.

## Human Approval Requirement

All containment actions beyond immediate network isolation (account
suspension, credential revocation, forensic imaging) require explicit
human approval from the security team lead, even in automated
workflows. This is a high-risk action category with zero tolerance for
autonomous execution.

## Post-Incident

A post-incident review is required for all confirmed security incidents,
documenting root cause, timeline, and remediation, to be added to the
Windows Update Compatibility Guide or equivalent reference if the root
cause is a software regression.
