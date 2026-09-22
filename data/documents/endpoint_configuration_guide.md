---
document_type: guide
department: IT Operations
version: "1.0"
access_level: standard
---

# Endpoint Configuration Guide

## Standard Managed Device Baseline

All managed laptops/desktops should have:

- Disk encryption enabled (BitLocker on Windows, FileVault on macOS).
- EndpointGuard EDR agent installed and reporting.
- CorpVPN Client at a supported version (4.11.0 or later).
- Automatic OS updates enabled with a 7-day deferral for feature updates.

## Configuration Drift

Devices that have not checked in (last_seen) within 14 days should be
flagged for review — they may be missing critical security updates and
their configuration state cannot be trusted.

## New Device Provisioning

New devices are provisioned with the current supported software baseline
automatically. Manual installation of VPN/EDR clients outside the
provisioning pipeline is discouraged as it risks version drift from the
supported baseline.
