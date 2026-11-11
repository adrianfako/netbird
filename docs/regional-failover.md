---
type: "Architecture"
title: "Regional failover"
description: "Agreed scope and acceptance for community NetBird regional failover."
tags: [networking, netbird, availability]
timestamp: "2026-11-11"
---

# Regional failover

Operator scope: owned infrastructure in eu-2, eu-6 and homelab. Tenant machines
and eu-8 are excluded from initial enrollment. Each site has a public IP and
operator-controlled firewall. Existing WireGuard remains the recovery path.

## Decisions

- Dedicated Linux VM per site: `infra-eu-2-netbird`, `infra-eu-6-netbird`,
  `infra-homelab-netbird`. Initial budget per VM: 2 vCPU, 4 GiB RAM, 40 GiB
  local SSD; validate against measured service and replication load.
- Server services use pinned Docker images and Compose. Host baseline and
  fencing use Ansible. Native Linux clients and OPNsense plugins are separate
  from server containers.
- Dashboard replicas and regional relays run in all three sites. Dashboard
  browser requests use one stable Management API address. Regional ingress
  routes Management and Signal to the elected active instance.
- Use health-checked endpoint failover, not unfiltered DNS round robin. DNS
  caches and existing connections still delay failover; measure recovery from
  real clients. A shared ingress or DNS service must not introduce a new
  single-site dependency. Provider selection follows current DNS inventory.
- Target one active community Management/Signal pair with fenced promotion.
  This is a hypothesis to prove in the lab, not a supported upstream HA mode.
  Do not start independent managers against shared storage and call it HA.
- Coordination and state replication must work without NetBird. Reuse an
  independently verified underlay, not the overlay being recovered.
- Dockhand provides fleet visibility and controls. Its homelab outage must not
  stop service startup, promotion, monitoring collection or SSH recovery.
- Keep upstream history and an `upstream` remote. Change community code only
  when a failing behavioral experiment proves deployment orchestration cannot
  satisfy the requirement. Do not copy proprietary Enterprise implementation.

## Ownership

| Repository | Responsibility |
| --- | --- |
| netbird | Upstream source, focused source changes, reproducible builds, lab checks |
| infrastructure | VM inventory, addressing, DNS and OPNsense/PVE policy |
| ansible | VM provisioning, host baseline, Docker and host fencing |
| depot | Production Compose artifacts, per-host manifests, SOPS service secrets and Dockhand enrollment |

Plans, decisions and operator procedures stay under `/docs` in their owning
repository. Configuration and tests define actual deployed topology; this
document records intent and constraints, not a second inventory. Preserve
upstream documents and licenses in place to keep upstream merges manageable.
The dashboard is a separate upstream repository: use its pinned published image
initially; fork it separately only for UI source changes.

## Approaches

Chosen: community deployment with automatic active/passive failover. It permits
brief controller interruption and minimizes maintained source changes.
Enterprise offers upstream-supported active/active Management and Signal but
is outside this build. Building community active/active is deferred until
measured failover proves insufficient; it requires distributed live state,
not merely database replication or a load balancer.

## Acceptance before enrollment

The lab must exercise actual community binaries, persistent state and clients.
Simulated leader-election tests alone do not prove NetBird failover.

1. Loss of each entire region, including its controller, database replica,
   quorum voter, ingress and relay: remaining two sites can enroll a fresh peer,
   update policy and reconnect peers through the same public service identity.
   Fresh authentication is part of this check only after the chosen identity
   provider's regional resilience is established as a prerequisite.
2. Two-versus-one partition: isolated site loses write authority; at most one
   controller is admitted. An unfenceable former leader prevents promotion.
3. Full quorum loss: no new writes or promotion; report degraded availability.
4. Database promotion preserves acknowledged policy changes, peer identities,
   encryption keys and authentication/session configuration. Choose replication
   and fail-closed behavior to satisfy this, rather than claiming asynchronous
   replication guarantees zero loss.
5. Rejoining former leader cannot overwrite newer state. Repeat failover during
   a policy write and controller restart.
6. Dashboard page, API and authentication readiness are checked separately.
   An accessible static dashboard with unreachable API is not a healthy service.
7. Relay loss recovers relayed connectivity; direct and relayed paths are tested
   separately. Report interruption rather than promising preserved TCP sessions.
8. Dockhand and NetBird overlay can both be unavailable while SSH recovery and
   control-plane coordination remain reachable.

Measure controller recovery, client reconnect and policy propagation separately.
No numeric recovery guarantee until measured. Existing authorization must not
be weakened to make recovery tests pass. Keycloak recovery is a separate
dependency for new logins; NetBird redundancy alone cannot guarantee it. A
single-site identity provider blocks the full regional-login acceptance claim
even if all NetBird component tests pass.

## References

Fork bootstrap secret scanning preserves upstream test material without blanket
test-directory exclusions. Historical exemptions identify exact upstream commit
fingerprints; current-file exemptions require the reviewed upstream file's full
SHA-256 hash in `.ci/upstream-fixtures.json`. Any changed file is scanned without
that exemption. These entries are public test fixtures and certificates, never
deployment credentials.

- [Dashboard API and authentication configuration](https://docs.netbird.io/selfhosted/maintenance/configuration-files)
- [Community external relays](https://docs.netbird.io/selfhosted/maintenance/scaling/set-up-external-relays)
- [Upstream Enterprise HA boundaries](https://docs.netbird.io/selfhosted/maintenance/scaling/high-availability)
- [Implementation plan](plan-regional-failover.md)
