---
document_type: sop
department: IT Operations
version: "1.3"
access_level: standard
---

# VPN Troubleshooting SOP

## Purpose

This Standard Operating Procedure defines the steps IT support staff and
Tier-1 agents should follow when a user reports an inability to connect to,
or maintain, a corporate VPN session.

## Scope

Applies to all CorpVPN Client installations on managed Windows, macOS, and
Linux endpoints.

## Section 1: Initial Triage

1. Confirm the user's CorpVPN Client version (Settings → About). Versions
   prior to 4.11.0 are end-of-life and should be upgraded before further
   troubleshooting.
2. Confirm the device's operating system and version. Certain OS releases
   are known to interact poorly with specific VPN client versions — check
   the Windows Update Compatibility Guide before proceeding.
3. Ask whether the issue started immediately after a software or OS update.
   This is the single strongest predictor of update-related VPN
   regressions.

## Section 2: Common Failure Patterns

### Error 691 (Authentication Rejected)

Error 691 almost always indicates a credential or authentication policy
issue, not a network problem. Steps:

1. Verify the user's domain password has not expired.
2. Verify MFA enrollment is active (see MFA Troubleshooting Guide).
3. Have the user fully quit and relaunch the VPN client, then re-enter
   credentials manually rather than using cached credentials.
4. If the device was recently updated to Windows 24H2, check the VPN Error
   Code Reference — this combination is a known problematic pairing with
   CorpVPN Client 4.12.1.

### Error 619 (Connection Dropped)

Typically caused by network instability or split-tunneling misconfiguration.

1. Confirm the user is not on a captive-portal network (hotel/airport Wi-Fi).
2. Check split-tunneling configuration; misconfigured routes can cause the
   tunnel to reset under load.
3. If on a managed device, confirm no conflicting VPN or firewall software
   is installed.

### Error 800 (Unable to Establish Connection)

1. Confirm outbound UDP 500/4500 and TCP 443 are not blocked by local
   network firewall.
2. Confirm the VPN gateway region the client is targeting is reporting
   "operational" status. Escalate to Network Operations if the gateway
   itself is degraded.

## Section 3: Escalation Criteria

Escalate to Tier 2 / Network Operations if:

- The issue affects more than 3 users in the same office location
  simultaneously (possible gateway or ISP issue).
- The VPN gateway system status shows "degraded" or "outage".
- The user has already followed all Tier-1 steps above without resolution.

## Section 4: Resolution Documentation

All resolved VPN incidents must record:

- The root cause category (credential, network, client version, gateway).
- The exact remediation step that resolved the issue.
- Whether the issue is linked to a known problematic software version.

This data feeds the historical incident database used for pattern
detection across recurring VPN issues.
