"""Failure reports must replace an earlier successful live run."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import run


class FailureReporting(unittest.TestCase):
    def test_compose_timeout_replaces_previous_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / 'results.json'
            result.write_text('[{"passed":true}]')
            (root / '.env').write_text('NETBIRD_URL=https://example.invalid\nNETBIRD_LAB_PAT=test-placeholder\n')
            response = MagicMock()
            response.__enter__.return_value.status = 200
            with patch.object(run, 'ROOT', root), patch.object(run, 'RESULTS', result), \
                    patch('sys.argv', ['run.py', '--run']), \
                    patch.object(run.urllib.request, 'urlopen', return_value=response), \
                    patch.object(run, 'API'), \
                    patch.object(run, 'compose', side_effect=subprocess.TimeoutExpired('compose', 150)):
                with self.assertRaises(SystemExit) as stopped:
                    run.main()
            self.assertEqual(stopped.exception.code, 1)
            report = json.loads(result.read_text())
            self.assertFalse(report[-1]['passed'])
            self.assertEqual(report[-1]['error'], 'TimeoutExpired')


if __name__ == '__main__':
    unittest.main()
