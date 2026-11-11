#!/usr/bin/env python3
"""Initialize the owned lab controller; keep owner credentials and PAT in SOPS."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.error
import urllib.request


class API:
    def __init__(self, url, token=None):
        self.url = url.rstrip('/')
        self.token = token

    def call(self, method, path, body=None):
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Token ' + self.token
        request = urllib.request.Request(self.url + '/api' + path,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{method} {path}: HTTP {error.code}') from None
        except urllib.error.URLError:
            raise RuntimeError(f'{method} {path}: service unreachable') from None


def read_env(path):
    result = subprocess.run(['sops', '--decrypt', str(path)], text=True,
                            capture_output=True, check=True)
    lines = result.stdout.splitlines()
    values = dict(line.split('=', 1) for line in lines if line and not line.startswith('#') and '=' in line)
    return lines, values


def save_env(path, lines, additions):
    existing = dict(line.split('=', 1) for line in lines if line and not line.startswith('#') and '=' in line)
    if set(existing).intersection(additions):
        raise RuntimeError('Refusing to overwrite existing credential fields')
    content = '\n'.join(lines) + '\n' + ''.join(k + '=' + v + '\n' for k, v in additions.items())
    result = subprocess.run(['sops', '--encrypt', '--input-type', 'dotenv', '--output-type', 'dotenv',
                             '--filename-override', str(path), '/dev/stdin'], input=content,
                            text=True, capture_output=True, cwd=path.parent, check=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.netbird-', delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(result.stdout.encode())
    os.replace(temporary, path)


def initialize(url, path):
    api = API(url)
    status = api.call('GET', '/instance')
    lines, values = read_env(path)
    if status['setup_required']:
        if values.get('NETBIRD_LAB_PAT'):
            raise RuntimeError('Instance state was reset; investigate before recreating owner')
        result = api.call('POST', '/setup', {
            'email': values['NETBIRD_ADMIN_EMAIL'],
            'password': values['NETBIRD_ADMIN_PASSWORD'],
            'name': 'NetBird Lab', 'create_pat': True, 'pat_expire_in': 1,
        })
        token = result.get('personal_access_token')
        if not token:
            raise RuntimeError('Owner created without PAT; recover through dashboard login')
        save_env(path, lines, {'NETBIRD_LAB_PAT': token})
        values['NETBIRD_LAB_PAT'] = token
        print('Initialized owner; one-day lab PAT saved encrypted', flush=True)
    if not values.get('NETBIRD_LAB_PAT'):
        raise RuntimeError('Initialized instance has no stored lab PAT')
    api.token = values['NETBIRD_LAB_PAT']
    peers = api.call('GET', '/peers')
    print(f'Authenticated lab API; {len(peers)} peers', flush=True)
    return api


def groups_in(rule, field):
    return [group['id'] if isinstance(group, dict) else group for group in rule.get(field, [])]


def ensure_lab(api, path):
    lines, values = read_env(path)
    group = next((g for g in api.call('GET', '/groups') if g['name'] == 'netbird-lab'), None)
    if group is None:
        group = api.call('POST', '/groups', {'name': 'netbird-lab', 'peers': []})
    group_id = group['id']
    policies = api.call('GET', '/policies')
    policy = next((p for p in policies if p['name'] == 'netbird-lab-only'), None)
    if policy is None:
        if api.call('GET', '/peers'):
            raise RuntimeError('Existing peers found before lab isolation; review policy manually')
        for old in policies:
            if not old.get('enabled'):
                continue
            if old['name'].lower() != 'default':
                raise RuntimeError('Unexpected existing policy; refusing to change it')
            rules = []
            for rule in old['rules']:
                rules.append({**{k: rule[k] for k in ('name', 'action', 'bidirectional', 'protocol')},
                              'enabled': False, 'sources': groups_in(rule, 'sources'),
                              'destinations': groups_in(rule, 'destinations')})
            api.call('PUT', '/policies/' + old['id'],
                     {'name': old['name'], 'enabled': False, 'rules': rules})
        policy = api.call('POST', '/policies', {
            'name': 'netbird-lab-only', 'enabled': True,
            'rules': [{'name': 'Lab peers only', 'enabled': True, 'action': 'accept',
                       'bidirectional': True, 'protocol': 'all',
                       'sources': [group_id], 'destinations': [group_id]}],
        })
    additions = {}
    for key, value in (('NETBIRD_LAB_GROUP_ID', group_id), ('NETBIRD_LAB_POLICY_ID', policy['id'])):
        if key not in values:
            additions[key] = value
    if 'NETBIRD_LAB_SETUP_KEY' not in values:
        key = api.call('POST', '/setup-keys', {
            'name': 'regional-failover-disposable-lab', 'type': 'reusable',
            'expires_in': 86400, 'usage_limit': 2, 'ephemeral': True,
            'auto_groups': [group_id],
        })
        additions['NETBIRD_LAB_SETUP_KEY'] = key['key']
    if additions:
        save_env(path, lines, additions)
    print('Lab group/policy ready; disposable enrollment limited to two peers', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://netbird.ops.eu-6.infra.8000.studio')
    parser.add_argument('--secrets-file', type=Path, required=True)
    parser.add_argument('--initialize', action='store_true')
    args = parser.parse_args()
    if not args.initialize:
        print('Dry run: pass --initialize to create lab owner, policy and enrollment key')
        return
    try:
        api = initialize(args.url, args.secrets_file.resolve())
        ensure_lab(api, args.secrets_file.resolve())
    except (RuntimeError, subprocess.CalledProcessError, KeyError) as error:
        print('Lab bootstrap stopped:', str(error) if isinstance(error, RuntimeError) else type(error).__name__)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
