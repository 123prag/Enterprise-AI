---
document_type: reference
department: IT Operations
version: "1.1"
access_level: standard
---

# VPN Error Code Reference

A quick-lookup reference for CorpVPN Client error codes. For remediation
steps, see the VPN Troubleshooting SOP.

| Code | Meaning | Likely Cause | Known Bad Combination |
|------|---------|--------------|------------------------|
| 691  | Authentication rejected | Expired password, MFA failure, stale cached credentials | CorpVPN Client 4.12.1 + Windows 24H2 |
| 619  | Connection dropped mid-session | Network instability, split-tunnel misconfiguration | — |
| 800  | Unable to establish connection | Firewall blocking UDP 500/4500, gateway outage | — |
| 809  | No response from gateway | Gateway degraded/outage, DNS resolution failure | — |
| 720  | No PPP control protocols configured | Corrupted client installation | — |

## Known Problematic Version Pairing

**CorpVPN Client 4.12.1 on Windows 24H2** has a confirmed regression where
the client's credential cache is invalidated during the Windows 24H2
in-place upgrade, causing repeated Error 691 on first connection attempt
after the update. This was first observed in incident clusters shortly
after 24H2 rollout began.

**Workaround:** Fully uninstall and reinstall CorpVPN Client after
completing the Windows 24H2 upgrade, rather than relying on the existing
installation. A permanent fix is tracked in CorpVPN Client 5.0.0 release
notes.

## Escalation Note

If a user reports Error 691 and their device shows Windows 24H2 with
CorpVPN Client 4.12.1, this reference should be surfaced immediately —
it explains the majority of post-24H2-rollout VPN tickets.
