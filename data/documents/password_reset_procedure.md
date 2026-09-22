---
document_type: sop
department: IT Operations
version: "1.0"
access_level: standard
---

# Password Reset Procedure

## Self-Service Reset

1. Direct the user to the self-service portal.
2. Confirm they are checking the correct recovery email/phone on file.
3. Check spam/junk folders — the reset email sender is frequently
   auto-filtered by third-party mail clients.

## Reset Email Never Received — Diagnostic Steps

1. Confirm the recovery email on file is current (not a former manager's
   email or a typo).
2. Resend the reset email and confirm the mail queue shows successful
   delivery, not just "sent".
3. If the domain-level mail filter is blocking the sender, escalate to
   the mail administration team to whitelist the password-reset sender
   domain.

## Manual Reset by IT Staff

Manual resets require identity verification (manager confirmation or
photo ID check for remote staff) and must be logged with the verification
method used. This is a security-sensitive action.

## Related

See MFA Troubleshooting Guide if the user's account also requires MFA
re-enrollment after the reset.
