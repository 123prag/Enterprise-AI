---
document_type: sop
department: Security
version: "1.0"
access_level: standard
---

# Endpoint Security SOP

## False Positive Quarantine (EDR-509)

1. Verify the flagged file/process against the current threat intelligence
   feed — false positives typically match a benign but recently-changed
   internal tool signature.
2. Do NOT release a quarantined item without security team sign-off if the
   flagged item involves a credential store, browser extension, or
   scripting engine (PowerShell, wscript).
3. If confirmed false positive, whitelist the specific hash (not the whole
   application) and document the justification.

## Disk Encryption Non-Compliance

1. Confirm the device actually has encryption enabled locally
   (BitLocker/FileVault status) — the management console can lag by
   several hours.
2. If genuinely non-compliant, this is treated as medium severity minimum
   and must be remediated within 24 hours per policy.

## Antivirus Definition Update Failures

1. Confirm the device has network access to the update distribution
   server.
2. Manually trigger a definition update.
3. If failures persist across multiple devices, escalate — this may
   indicate a distribution server issue rather than individual device
   problems.

## Escalation

Any suspected active compromise, malware execution (not just detection),
or unauthorized access must be escalated per the Security Incident
Response SOP immediately — do not attempt to remediate through standard
endpoint tooling first.
