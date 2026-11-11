---
type: "Guide"
title: "Operate the private NetBird lab"
description: "Access and verify the initial controller without changing existing fleet routes."
tags: [networking, netbird]
timestamp: "2026-11-11"
---

# Operate the private NetBird lab

For the fleet operator. Open <https://netbird.ops.eu-6.infra.8000.studio> over
existing fleet VPN. Initial owner is `admin@netbird.local`; its password and
one-day lab API token live in Depot's SOPS-encrypted
`lighthouse/netbird/env/infra-eu-6-netbird.env`. Do not paste credentials into chat.

Only eu-6 runs the controller. Other dashboards use that same API. Losing eu-6
currently loses enrollment and policy updates; regional dashboard replicas are
not controller failover. Existing WireGuard remains recovery access.

Run `tests/regional-failover/bootstrap.py --help` from the operator checkout.
Initialization requires explicit `--initialize`; it refuses to overwrite owner
credentials or reset an initialized controller. Never initialize a second owner
to work around lost state.

The traffic harness runs on the dedicated eu-6 VM, not laptop host networking.
Deliver its `.env` privately with mode 600: URL, lab PAT, group/policy IDs and
`NB_SETUP_KEY` from the encrypted lab setup key. Run `run.py --run` there.
It starts two disposable peers, exercises actual traffic and policy denial,
restores policy in a `finally` block, and saves results under
`/mnt/data/netbird/lab/results.json`. Failure does not justify broadening fleet
firewall rules. Setup key permits two enrollments and expires after one day;
existing persisted peer identities survive container restarts.

No regional subnets are advertised. Lab policy permits only lab-group members.
Keep regional pilot enrollments limited to the three new VMs until traffic
verification and later failover work pass.
