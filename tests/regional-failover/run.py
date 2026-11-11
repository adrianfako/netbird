#!/usr/bin/env python3
"""Exercise real disposable peers; no host networking or regional routes."""
import argparse
import ipaddress
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

from bootstrap import API

ROOT = Path(__file__).resolve().parent


def compose(*args, timeout=150):
    result = subprocess.run(['sudo', '-n', 'docker', 'compose', *args], cwd=ROOT,
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Compose operation failed: ' + args[0])
    return result.stdout


def wait_for(check, seconds=90):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result = check()
            if result:
                return result
        except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired):
            pass
        time.sleep(2)
    raise RuntimeError('Condition did not recover within deadline')


def peer_ip(name):
    status = json.loads(compose('exec', '-T', name, 'netbird', 'status', '--json', timeout=10))
    if not status.get('management', {}).get('connected') or not status.get('signal', {}).get('connected'):
        return None
    address = status.get('netbirdIp')
    return str(ipaddress.ip_interface(address).ip) if address else None


def fetch_from_a(address):
    return compose('exec', '-T', 'peer-a', 'wget', '-qO-', '-T', '3', f'http://{address}:8080/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print('Pass --run on dedicated lab VM; .env must contain scoped lab credentials')
        return
    values = dict(line.split('=', 1) for line in (ROOT/'.env').read_text().splitlines()
                  if line and not line.startswith('#') and '=' in line)
    api = API(values['NETBIRD_URL'], values['NETBIRD_LAB_PAT'])
    results = []

    def check(name, operation):
        started = time.monotonic()
        operation()
        results.append({'test': name, 'passed': True, 'seconds': round(time.monotonic()-started, 3)})
        print('PASS', name, flush=True)

    try:
        def https_ready():
            with urllib.request.urlopen(values['NETBIRD_URL'], timeout=15) as response:
                assert response.status == 200
        check('dashboard HTTPS and certificate', https_ready)
        check('authenticated management API', lambda: api.call('GET', '/peers'))
        compose('up', '-d')
        first_a = wait_for(lambda: peer_ip('peer-a'))
        first_b = wait_for(lambda: peer_ip('peer-b'))
        check('both peer sessions connected', lambda: (ipaddress.ip_address(first_a), ipaddress.ip_address(first_b)))
        check('A to B overlay ping', lambda: compose('exec', '-T', 'peer-a', 'ping', '-c', '3', '-W', '2', first_b))
        check('B to A overlay ping', lambda: compose('exec', '-T', 'peer-b', 'ping', '-c', '3', '-W', '2', first_a))
        def http_ready():
            assert wait_for(lambda: fetch_from_a(first_b) == 'netbird-lab-ok')
        check('overlay HTTP payload', http_ready)
        policy_id = values['NETBIRD_LAB_POLICY_ID']
        group_id = values['NETBIRD_LAB_GROUP_ID']
        def set_policy(enabled):
            api.call('PUT', '/policies/' + policy_id, {
                'name': 'netbird-lab-only', 'enabled': enabled,
                'rules': [{'name': 'Lab peers only', 'enabled': enabled,
                           'action': 'accept', 'bidirectional': True, 'protocol': 'all',
                           'sources': [group_id], 'destinations': [group_id]}]})
        def policy_denies():
            set_policy(False)
            try:
                def denied():
                    if not peer_ip('peer-a') or not peer_ip('peer-b'):
                        return False
                    local = compose('exec', '-T', 'echo', 'wget', '-qO-', '-T', '3', 'http://127.0.0.1:8080/')
                    if local != 'netbird-lab-ok':
                        return False
                    try:
                        fetch_from_a(first_b)
                        return False
                    except RuntimeError:
                        return True
                assert wait_for(denied, 45)
            finally:
                set_policy(True)
        check('disabled lab policy denies fresh HTTP', policy_denies)
        check('restored policy restores payload', http_ready)
        def restart_peer():
            compose('restart', 'peer-b', 'echo')
            assert wait_for(lambda: peer_ip('peer-b')) == first_b
            http_ready()
        check('peer restart retains identity and recovers traffic', restart_peer)
        def no_routes():
            assert api.call('GET', '/routes') == []
            assert api.call('GET', '/networks') == []
        check('no regional subnet advertisements', no_routes)
    except (RuntimeError, AssertionError, KeyError, urllib.error.URLError) as error:
        results.append({'test': 'execution', 'passed': False, 'error': type(error).__name__})
        print('FAIL', type(error).__name__, flush=True)
    output = Path('/mnt/data/netbird/lab/results.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2)+'\n')
    print(f'{sum(r["passed"] for r in results)}/{len(results)} checks passed', flush=True)
    raise SystemExit(0 if results and all(r['passed'] for r in results) else 1)


if __name__ == '__main__':
    main()
