#!/usr/bin/env python3
"""Issue one-use enrollment for the three dedicated regional lab VMs only."""
import argparse
from pathlib import Path
from bootstrap import API, read_env, save_env

HOSTS = ('infra-eu-2-netbird', 'infra-eu-6-netbird', 'infra-homelab-netbird')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=HOSTS, required=True)
    parser.add_argument('--owner-secrets', type=Path, required=True)
    parser.add_argument('--host-secrets', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print('Dry run: one-use regional enrollment; --apply required')
        return
    _, owner = read_env(args.owner_secrets.resolve())
    target = args.host_secrets.resolve()
    if target.name != args.host + '.env':
        raise RuntimeError('Host secret filename must match selected VM')
    lines, values = read_env(target)
    if values.get('NETBIRD_REGIONAL_SETUP_KEY'):
        print('Enrollment already stored; refusing to rotate or reissue')
        return
    api = API('https://netbird.ops.eu-6.infra.8000.studio', owner['NETBIRD_LAB_PAT'])
    groups = [g for g in api.call('GET', '/groups') if g['name'] == 'netbird-regions']
    group = groups[0] if groups else api.call('POST', '/groups', {'name': 'netbird-regions', 'peers': []})
    policies = [p for p in api.call('GET', '/policies') if p['name'] == 'netbird-regions-only']
    if not policies:
        api.call('POST', '/policies', {
            'name': 'netbird-regions-only', 'enabled': True,
            'rules': [{'name': 'Dedicated regional VMs', 'enabled': True, 'action': 'accept',
                       'bidirectional': True, 'protocol': 'all',
                       'sources': [group['id']], 'destinations': [group['id']]}],
        })
    key = api.call('POST', '/setup-keys', {
        'name': args.host, 'type': 'one-off', 'usage_limit': 1,
        'expires_in': 86400, 'ephemeral': False, 'auto_groups': [group['id']],
    })
    save_env(target, lines, {'NETBIRD_REGIONAL_SETUP_KEY': key['key']})
    print('One-use regional enrollment saved encrypted:', args.host)


if __name__ == '__main__':
    main()
