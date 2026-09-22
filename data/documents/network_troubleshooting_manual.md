---
document_type: guide
department: IT Operations
version: "1.0"
access_level: standard
---

# Network Troubleshooting Manual

## Intermittent Wi-Fi Packet Loss

1. Identify the access point the user is connected to (via device network
   settings) and check for known congestion on that AP.
2. Ask if the issue correlates with time of day (peak usage congestion)
   or location (dead zone).
3. If isolated to one user, have them forget and rejoin the Wi-Fi network.
4. If affecting a whole floor/office, escalate to Network Operations —
   likely an access point or switch issue, not a client-side problem.

## DNS Resolution Timeouts

1. Confirm the user's device is using the corporate DNS servers (not a
   stale public DNS from a previous network).
2. Flush local DNS cache.
3. Check Internal DNS system status — if degraded, this is a
   infrastructure issue, not a device issue, and should be escalated
   immediately with all affected users' tickets linked together.

## VoIP Call Quality Issues

1. Confirm QoS tagging is enabled on the user's network switch port.
2. Rule out VPN split-tunneling routing voice traffic through the tunnel
   unnecessarily.
3. Test from a different physical location — narrows down whether the
   issue is location-specific network congestion.
