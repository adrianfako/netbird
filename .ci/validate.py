#!/usr/bin/env python3
"""Self-contained foundation checks and explicit offline project adapters.

Canonical source: agent-kit/tools/delivery/baseline_runner.py. No eval or shell.
A green foundation alone never means application tests passed.
"""
import ast
import csv
import json
import math
import os
import re
import tomllib
from urllib.parse import unquote, urlsplit
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MAX_FILE_BYTES = 8 * 1024 * 1024
PROFILES = {'python', 'node', 'php', 'infra', 'docs', 'data', 'mixed'}
IGNORED = {'.git', 'node_modules', '.venv', 'vendor', '__pycache__'}


def files(root):
    result = subprocess.run(['git', '-c', 'core.fsmonitor=false', 'ls-files', '-z'], cwd=root, capture_output=True)
    if result.returncode == 0:
        return [root / name for name in result.stdout.decode().split('\0') if name and (root / name).is_file() and not (root / name).is_symlink() and (root / name).resolve().is_relative_to(root.resolve())]
    paths = []
    for parent, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name not in IGNORED]
        paths.extend(Path(parent) / name for name in names if not (Path(parent) / name).is_symlink())
    return paths


def bounded_read(path):
    with path.open('rb') as stream:
        content = stream.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError(f'INCOMPLETE: file exceeds {MAX_FILE_BYTES} byte parsing limit')
    return content


def markdown_prose(text):
    lines, fence = [], None
    for line in text.splitlines():
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return re.sub(r'(`+).*?\1', '', '\n'.join(lines), flags=re.S)


def application_paths(root):
    suffixes = {'.py', '.php', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.go', '.rs', '.tf', '.sh'}
    manifests = {'package.json', 'pyproject.toml', 'composer.json', 'Cargo.toml', 'go.mod', 'Chart.yaml', 'ansible.cfg'}
    return [path.relative_to(root).as_posix() for path in files(root)
            if not set(path.relative_to(root).parts).intersection(IGNORED | {'.ci', '.gitea', '.github'})
            and (path.suffix in suffixes or path.name in manifests)]


def foundation(root):
    failures = []
    for path in files(root):
        if any(part in IGNORED for part in path.relative_to(root).parts):
            continue
        try:
            content = bounded_read(path) if path.suffix in ('.py', '.json', '.toml', '.md', '.yaml', '.yml') else None
            if path.suffix == '.py':
                ast.parse(content, filename=str(path.relative_to(root)))
            elif path.suffix == '.json':
                if path.parent.name == '.vscode' and path.name in {
                        'settings.json', 'tasks.json', 'launch.json', 'extensions.json'}:
                    # VS Code configuration is JSON with comments and trailing
                    # commas. Preserve strings during both normalization passes.
                    quoted = r'"(?:\\.|[^"\\])*"'
                    text = content.decode('utf8')
                    text = re.sub(quoted + r'|//[^\r\n]*|/\*[\s\S]*?\*/',
                                  lambda m: m[0] if m[0].startswith('"') else ' ', text)
                    text = re.sub(quoted + r'|,\s*([}\]])',
                                  lambda m: m[0] if m[0].startswith('"') else m[1], text)
                    content = text
                json.loads(content)
            elif path.suffix == '.toml':
                tomllib.loads(content.decode('utf8'))
            elif path.suffix in ('.yaml', '.yml'):
                try:
                    import yaml
                except ImportError:
                    raise ValueError('INCOMPLETE: install PyYAML==6.0.3 to validate YAML') from None
                try:
                    list(yaml.load_all(content, Loader=yaml.BaseLoader))
                except yaml.YAMLError:
                    raise ValueError('invalid YAML syntax') from None
            elif path.suffix == '.md':
                for link in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', markdown_prose(content.decode('utf8'))):
                    target = urlsplit(link.strip('<>'))
                    if target.scheme or target.netloc or not target.path or target.path.startswith('/'):
                        continue
                    destination = (path.parent / unquote(target.path)).resolve()
                    if not destination.is_relative_to(root.resolve()):
                        print('UNVERIFIED external repository link:', target.path, flush=True)
                        continue
                    if not destination.exists():
                        raise ValueError('missing local link: ' + target.path)
            elif path.suffix == '.csv':
                # SOPS binary-mode files retain their plaintext extension but
                # contain a JSON envelope. Validate that container, not ciphertext
                # as CSV; encrypted row contents cannot be checked without keys.
                with path.open('rb') as stream:
                    json_candidate = stream.read(64).lstrip().startswith(b'{')
                if json_candidate:
                    try:
                        envelope = json.loads(bounded_read(path))
                    except (ValueError, UnicodeError):
                        envelope = None
                    if (isinstance(envelope, dict) and set(envelope) == {'data', 'sops'}
                            and isinstance(envelope['sops'], dict)
                            and isinstance(envelope['data'], str)
                            and envelope['data'].startswith('ENC[AES256_GCM,')
                            and envelope['data'].endswith(']')):
                        print('UNVERIFIED encrypted CSV contents:', path.relative_to(root), flush=True)
                        continue
                with path.open(newline='') as stream:
                    rows = csv.reader(stream, strict=True)
                    width = None
                    for row in rows:
                        width = len(row) if width is None else width
                        if len(row) != width:
                            raise ValueError('inconsistent CSV field count')
        except (ValueError, SyntaxError, UnicodeError, OSError, csv.Error) as exc:
            failures.append(f'{path.relative_to(root)}: {exc}')
    for failure in failures:
        print('FAIL foundation:', failure, flush=True)
    return not failures


def run(root=ROOT):
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True)
    print('commit:', commit.stdout.strip() if commit.returncode == 0 else 'unavailable', flush=True)
    try:
        manifest = json.loads(bounded_read(root / '.ci/validation.json'))
        if not isinstance(manifest, dict) or type(manifest.get('version')) is not int or manifest['version'] != 1:
            raise ValueError('unsupported manifest version')
        if manifest.get('profile') not in PROFILES:
            raise ValueError('unsupported manifest profile')
        success = foundation(root)
        status = manifest.get('adapter_status')
        if status not in ('configured', 'foundation-only') or status == 'configured' and not manifest.get('checks'):
            print('INCOMPLETE: no project suite adapter configured', flush=True)
            return 1
        if status == 'foundation-only':
            if manifest.get('profile') not in ('docs', 'data'):
                raise ValueError('foundation-only is limited to docs/data')
            if application_paths(root):
                print('INCOMPLETE: application code/manifests require a behavioral adapter', flush=True)
                return 1
            print('FOUNDATION ONLY: no behavioral test claim', flush=True)
        for check in manifest.get('checks', []):
            argv = check['argv']
            if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv):
                raise ValueError('check argv must be a nonempty string list')
            cwd = (root / check.get('cwd', '.')).resolve()
            if not cwd.is_relative_to(root.resolve()):
                raise ValueError('check cwd escapes repository')
            timeout = float(check.get('timeout', 300))
            if not math.isfinite(timeout) or timeout <= 0 or timeout > 900:
                raise ValueError('check timeout must be between 0 and 900 seconds')
            name = check.get('name', 'project-suite')
            print('RUN', name, json.dumps(argv), flush=True)
            try:
                result = subprocess.run(argv, cwd=cwd, timeout=timeout)
                print('STATUS', name, result.returncode, flush=True)
                success &= result.returncode == 0
            except subprocess.TimeoutExpired:
                print('TIMEOUT', name, flush=True)
                success = False
        return 0 if success else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('FAIL baseline:', exc, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(run())
