---
document_type: guide
department: IT Operations
version: "1.0"
access_level: standard
---

# MFA Troubleshooting Guide

## Push Notifications Not Arriving

1. Confirm the mobile authenticator app has notification permissions
   enabled at the OS level.
2. Confirm the device has network connectivity (Wi-Fi or cellular).
3. Have the user manually open the authenticator app and pull to refresh
   rather than waiting for a push.
4. If the user recently changed phones, confirm MFA was re-enrolled on
   the new device — a common cause of "silent" MFA failures.

## MFA Enrollment Reset

If a user has lost their MFA device entirely:

1. Verify the user's identity through a secondary channel (manager
   confirmation or ID verification) before resetting.
2. Reset MFA enrollment in the identity provider console.
3. Have the user re-enroll immediately using the new device.
4. Document the reset in the ticket with the verification method used —
   this is a security-sensitive action and must be auditable.

## Relationship to VPN Authentication

MFA failures are a common underlying cause of VPN Error 691. Always check
MFA enrollment status before assuming a VPN-specific root cause.
