---
type: "Plan"
title: "Regional failover implementation plan"
description: "Lab proof, provisioning and pilot sequence for owned three-region NetBird."
tags: [networking, netbird, availability]
timestamp: "2026-11-11"
---

# Regional failover implementation plan

**Goal:** Start dedicated lab VMs and a dashboard in owned eu-2, eu-6 and
homelab, prove isolated peer traffic, then develop community controller failover.
Preserve the existing recovery network.

**Operator sequencing, 2026-11-11:** Provision the three VMs first, with one
active eu-6 controller. Dashboard replicas are clients of that controller and
do not provide controller HA. Connect only these new hosts over existing
WireGuard; do not advertise regional subnets or enroll existing workloads.
Public ingress, production enrollment and automatic failover remain later work.

**Spec:** [Regional failover](regional-failover.md).

**Architecture:** Three dedicated Linux VMs, regional relays/dashboard replicas,
one fenced active Management/Signal pair. Actual upstream state and reconnect
behavior determine promotion mechanism; production follows lab evidence.

**Execution:** Native implementation in this session. Changes affecting source,
deployment and firewall policy land in their owning repos independently.

## Review focus

Partitions must not create two writable controllers. Promotion must not lose
acknowledged policy writes. Dashboard availability must include API and login
readiness. Relays must remain independently reachable. Recovery must work when
both Dockhand and the NetBird overlay are down.

## 1. Establish source and deployment baseline

- [x] Preserve upstream history in `CODE/fleet/netbird`, with `upstream` remote
  and operator remotes on Gitea/GitHub. Disable GitHub Actions before first push;
  preserve inherited workflows as upstream content, execute fleet CI on Gitea.
- [x] Record exact upstream commit and choose a stable release for the lab.
  Verify release source and server/dashboard image compatibility and digests.
- [ ] Trace Management persistent state and in-memory update channels, Signal
  peer registry, database migration startup, encryption/session keys and public
  endpoint configuration. Record only consequential blockers under `/docs`.
- [x] Inspect regional VM capacity, public IP/port use, DNS capabilities,
  Keycloak availability and independent coordination paths before assigning
  addresses. No guessed VM IDs, free public ports or DNS failover capability.

## 2. Prove active/passive behavior in an isolated lab

- [ ] Add `tests/regional-failover/compose.yml` and executable scenario runner
  under `tests/regional-failover/`. Use disposable networks/volumes and test
  identities. Never attach test clients to laptop host networking.
- [ ] Bring up actual Management/Signal, three relays, dashboard and persistent
  database with two disposable clients. Validate API policy changes and actual
  client traffic before introducing failover.
- [ ] Select database replication and lease/fencing implementation from observed
  state requirements. Replication must preserve acknowledged writes; promotion
  must prove former controller fenced. Keep one controller admitted at a time.
- [ ] Implement whole-region isolation (controller, database, quorum voter,
  ingress and relay together), node-stop, controller-stop, database-stop,
  asymmetric partition, quorum-loss and stale-node-rejoin scenarios. Assert controller exclusivity,
  durable policy and restored real client traffic, not container health alone.
- [ ] Report recovery times and blocked acceptance conditions under `/docs`.
  If deployment cannot meet acceptance, isolate smallest upstream code change
  and add a real reproducer before implementing it.
- [ ] Run bounded jobs with `agent-job`; move resource-heavy lab to existing
  Agents VM workflow if needed. Lab firewall mutations stay inside disposable
  environments; Agents/Kali must not administer fleet firewalls.

## 3. Provision dedicated lab hosts before traffic tests

- [x] Infrastructure: allocate three VMs in region `vms.yaml`, DNS and declared
  flows. Run host index with no gaps and region checks. Use existing provisioning
  procedures and Ansible; do not manually write generated inventory.
- [ ] Ansible: apply OS/Docker baseline and proven host fencing. Confirm SSH
  recovery independently from NetBird on each host.
- [x] Depot: add `lighthouse/netbird/compose.yml` and three host manifests.
  Pin images by digest, render per-host artifacts, use existing SOPS service-env
  convention and enroll Hawser/Alloy through existing tools.
- [ ] Set up regional HTTPS ingress and health-checked public endpoint using
  verified existing DNS capabilities. Relay public endpoints remain independent.
  Test protocols, TLS, streaming connections and cache effects externally.
- [ ] Firewall: preview YAML changes and apply only through repository firewall
  procedure with required operator approval. Preserve declared existing flows.

## 4. Pilot and controlled enrollment

- [ ] Validate fresh login, enrollment and policy enforcement through every
  regional dashboard and stable API endpoint with disposable pilot VM first.
  Establish chosen identity provider's resilience before claiming fresh logins
  survive each whole-region loss; a single-site IdP is a reported blocker.
- [ ] Repeat proven failover scenarios against production control nodes without
  changing existing client routes. Confirm Dockhand-independent recovery.
- [ ] Enroll laptop and explicitly selected owned infrastructure. Add OPNsense
  gateway integration only through reviewed fleet configuration procedure.
- [ ] Preserve working WireGuard recovery. Record actual measured recovery,
  rollback commands and unresolved dependencies under `/docs`; no automatic
  enrollment of tenant machines, eu-8 or unmanaged supplier networks.

## Delivery

Commit and push each verified unit through existing dual-home integration.
Documentation-only checks do not count as Go/runtime validation. Once source
changes exist, run upstream formatting/lint and focused behavioral/race checks;
build and test broader artifacts in bounded jobs before deployment.
