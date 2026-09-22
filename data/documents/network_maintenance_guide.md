---
document_type: guide
department: IT Operations
version: "1.0"
access_level: standard
---

# Network Maintenance Guide

## Scheduled Maintenance Windows

Network maintenance (switch firmware updates, AP reboots, gateway
failover tests) occurs Sundays 02:00–05:00 local time. Incidents
reported during this window for connectivity issues should first be
checked against the maintenance calendar before full triage.

## VPN Gateway Failover Testing

Quarterly failover tests may cause brief (under 60 second) VPN session
drops for users connected to the gateway under test. This is expected
and should not be logged as a defect unless the session fails to
reconnect automatically.

## Post-Maintenance Verification Checklist

1. Confirm all system_status entries return to "operational".
2. Spot-check VPN connectivity from at least one device per office
   location.
3. Confirm DNS resolution latency is within normal baseline.
