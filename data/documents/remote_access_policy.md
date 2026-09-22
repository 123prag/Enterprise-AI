---
document_type: policy
department: Security
version: "1.0"
access_level: standard
---

# Remote Access Policy

## VPN Access Requirements

- Access to internal systems from outside the corporate network requires
  an active VPN session using the current supported CorpVPN Client.
- MFA is mandatory for all VPN authentication; there are no exceptions
  for any role, including administrators.
- Split-tunneling is permitted only for pre-approved low-risk traffic
  categories (e.g. general web browsing); all traffic to internal systems
  must route through the tunnel.

## Device Requirements

Only managed devices meeting the Endpoint Configuration Guide baseline
may establish VPN connections. Unmanaged/personal devices are not
permitted for VPN access to internal systems.

## Configuration Changes

Any change to VPN gateway configuration, routing policy, or
split-tunneling rules is classified as a high-risk production
configuration change under the IT Service Management Policy and
requires Change Management approval plus human sign-off before
execution, regardless of urgency claimed by the requester.
