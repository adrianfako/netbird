import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('validate', Path(__file__).with_name('validate.py'))
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
scan_spec = importlib.util.spec_from_file_location('scanner', Path(__file__).with_name('gitleaks.py'))
scanner = importlib.util.module_from_spec(scan_spec)
scan_spec.loader.exec_module(scanner)


class TypeScriptConfigValidation(unittest.TestCase):
    def check_config(self, content):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tsconfig.json').write_text(content)
            with contextlib.redirect_stdout(io.StringIO()):
                return validator.foundation(root)

    def test_accepts_typescript_comments_and_trailing_commas(self):
        self.assertTrue(self.check_config('''{
          // Keep URLs and comment markers inside strings.
          "compilerOptions": {"baseUrl": "https://example.invalid/*",},
          /* Supported TypeScript config syntax. */
        }'''))

    def test_rejects_invalid_typescript_config(self):
        self.assertFalse(self.check_config('{"compilerOptions": {"strict": }}'))


class UpstreamFixtureVerification(unittest.TestCase):
    def test_changed_and_unlisted_files_are_not_exempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / 'fixture_test.go'
            fixture.write_bytes(b'public upstream test fixture')
            baseline = {fixture.name: hashlib.sha256(fixture.read_bytes()).hexdigest()}
            self.assertTrue(scanner.reviewed_fixture(root, fixture.name, baseline))
            self.assertFalse(scanner.reviewed_fixture(root, fixture.name, {}))
            fixture.write_bytes(b'new credential in changed fixture')
            self.assertFalse(scanner.reviewed_fixture(root, fixture.name, baseline))

    def test_symlinks_are_not_exempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source').write_bytes(b'public fixture')
            (root / 'link').symlink_to(root / 'source')
            baseline = {'link': hashlib.sha256(b'public fixture').hexdigest()}
            self.assertFalse(scanner.reviewed_fixture(root, 'link', baseline))


if __name__ == '__main__':
    unittest.main()
