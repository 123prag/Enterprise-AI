---
document_type: release_notes
department: Engineering
version: "1.0"
access_level: standard
---

# Software Release Notes

## CorpVPN Client 5.0.0

- Fixes credential cache invalidation bug affecting 4.12.1 on Windows
  24H2 (root cause of widespread Error 691 reports).
- Improved split-tunneling stability, reducing Error 619 disconnects.
- New: automatic client update from 4.11.x and later.

## CorpVPN Client 4.12.1

- Added support for Windows 24H2 (contains a known regression — see
  VPN Error Code Reference).
- Minor UI fixes.

## EndpointGuard EDR 9.4.0

- Reduced false-positive rate for scripting-engine detections.
- Compliance status now updates within 4 hours of OS upgrade (down from
  24 hours in 9.2.0/9.3.1).

## SSO Connector 2.2.0

- Reduced role-change propagation delay from 30 minutes to 5 minutes.
- Fixed intermittent MFA push delivery failures on certain carrier
  networks.
