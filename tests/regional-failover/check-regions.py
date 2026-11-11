#!/usr/bin/env python3
"""Read-only verification of the three dedicated regional pilot peers."""
import concurrent.futures
import ipaddress
import json
import subprocess

HOSTS = ('infra-eu-2-netbird', 'infra-eu-6-netbird', 'infra-homelab-netbird')


def ssh(host, command):
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                             host, command], capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise RuntimeError('SSH probe failed: ' + host)
    return result.stdout


def status(host):
    value = json.loads(ssh(host, 'sudo docker exec netbird-netbird-peer-1 netbird status --json'))
    if not value.get('management', {}).get('connected') or not value.get('signal', {}).get('connected'):
        raise RuntimeError('Control connection incomplete: ' + host)
    address = str(ipaddress.ip_interface(value['netbirdIp']).ip)
    routes = json.loads(ssh(host, 'ip -j route show default'))
    if len(routes) != 1 or routes[0].get('dev') != 'eth0':
        raise RuntimeError('Default route changed: ' + host)
    return address


def main():
    report = {'peers': {}, 'traffic': [], 'passed': False}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            report['peers'] = dict(zip(HOSTS, pool.map(status, HOSTS)))
        if len(set(report['peers'].values())) != len(HOSTS):
            raise RuntimeError('Duplicate peer identity')
        for source in HOSTS:
            for target in HOSTS:
                if source == target:
                    continue
                # Address is parsed by ipaddress above, never arbitrary shell input.
                output = ssh(source, 'ping -c 3 -W 2 ' + report['peers'][target])
                report['traffic'].append({'from': source, 'to': target, 'passed': True,
                                          'summary': output.splitlines()[-1]})
        report['passed'] = True
    except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
