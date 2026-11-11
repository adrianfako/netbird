#!/usr/bin/env python3
"""Install checksum-pinned Gitleaks in a temporary directory and scan cwd.

Only file, line and rule identifiers are printed. Raw scanner output and secret
fields never reach logs. Canonical source: agent-kit/tools/delivery/gitleaks_scan.py.
"""
import hashlib
import io
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen

VERSION = '8.30.1'
URL = 'https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz'
SHA256 = '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'
MAX_BYTES = 64 * 1024 * 1024


class ScanError(Exception):
    """Sanitized operational failure."""


def download():
    try:
        with urlopen(URL, timeout=30) as response:
            content = response.read(MAX_BYTES + 1)
    except Exception:
        raise ScanError('Pinned scanner download failed') from None
    if len(content) > MAX_BYTES:
        raise ScanError('Scanner download exceeds size limit')
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise ScanError('Pinned scanner checksum mismatch')
    return content


def install(content, directory):
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as archive:
            members, total_size = [], 0
            for index, member in enumerate(archive):
                total_size += member.size
                if index >= 128 or member.size < 0 or member.size > MAX_BYTES or total_size > 2 * MAX_BYTES:
                    raise ScanError('Scanner archive exceeds unpacked size limit')
                if member.name == 'gitleaks':
                    members.append(member)
            if len(members) != 1 or not members[0].isreg() or members[0].size > MAX_BYTES:
                raise ScanError('Scanner archive lacks one bounded regular gitleaks member')
            with archive.extractfile(members[0]) as source:
                binary = source.read(MAX_BYTES + 1)
            if len(binary) > MAX_BYTES:
                raise ScanError('Scanner binary exceeds size limit')
        path = directory / 'gitleaks'
        path.write_bytes(binary)
        path.chmod(0o700)
        return path
    except ScanError:
        raise
    except Exception:
        raise ScanError('Invalid scanner archive') from None


def scan(root):
    if sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise ScanError('Pinned scanner supports Linux x86_64 only')
    with tempfile.TemporaryDirectory(prefix='fleet-gitleaks-') as directory:
        directory = Path(directory)
        binary = install(download(), directory)
        report = directory / 'findings.json'
        try:
            # Discard raw output entirely: neither a subprocess exception nor its
            # stdout/stderr may disclose credential-bearing matches.
            result = subprocess.run([str(binary), 'dir', '--redact=100', '--no-banner',
                                     '--exit-code', '1', '--log-level=error',
                                     '--report-format=json', '--report-path', str(report), '.'],
                                    cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=900)
        except Exception:
            raise ScanError('Scanner execution failed') from None
        if result.returncode not in (0, 1):
            raise ScanError('Scanner operational failure')
        if result.returncode == 0:
            print('Gitleaks: no findings', flush=True)
            return 0
        try:
            if report.stat().st_size > MAX_BYTES:
                raise ValueError('oversized report')
            findings = json.loads(report.read_text())
            if not isinstance(findings, list) or not findings:
                raise ValueError('missing findings')
            rows = []
            for finding in findings:
                file, line, rule = finding['File'], finding['StartLine'], finding['RuleID']
                if not isinstance(file, str) or type(line) is not int or not isinstance(rule, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', rule):
                    raise ValueError('invalid finding metadata')
                rows.append({'file': file, 'line': line, 'rule': rule})
        except Exception:
            raise ScanError('Scanner findings report is invalid') from None
        for row in rows:
            print(json.dumps(row, ensure_ascii=True), flush=True)
        return 1


def main():
    try:
        return scan(Path.cwd())
    except ScanError as exc:
        print('Gitleaks:', exc, file=sys.stderr)
        return 2
    except Exception:
        print('Gitleaks: operational failure', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
