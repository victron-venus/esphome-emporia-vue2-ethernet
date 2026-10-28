"""Regression tests for malformed source and accidental publication."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
SPEC = importlib.util.spec_from_file_location('checks', Path(__file__).resolve().parents[1] / 'scripts/check.py')
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><title>Diagram</title><desc>Example</desc>{}</svg>'

class ParserTests(unittest.TestCase):
    def test_json_ambiguous_or_nonfinite(self):
        for text in ('{"c":{"x":1,"x":2}}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e999}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                checks.check_json(text)
        checks.check_json('{"zero":0,"missing":null}')

    def test_yaml_duplicates_and_cycles(self):
        for text in ('api:\n  reboot_timeout: 0s\n  reboot_timeout: 15min\n', 'loop: &loop [*loop]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                checks.check_yaml(text)

    def test_yaml_inert_tags_and_shared_aliases(self):
        checks.check_yaml('key: !secret absent\nfile: !include absent.yaml\n')
        checks.check_yaml('base: &base {enabled: true}\nfirst: *base\nsecond: *base\n')
        checks.check_yaml('on: {push: {}}\ntrue: separate-text-key\n')

    def test_svg_references_and_nonstatic_content(self):
        checks.check_svg(SVG.format('<defs><marker id="arrow"/></defs><path marker-end="url(#arrow)"/>'))
        for content in ('<path marker-end="url(#missing)"/>', '<g id="same"/><g id="same"/>', '<g onload="unused"/>', '<image href="https://example.invalid/image.png"/>'):
            text = SVG.format(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                checks.check_svg(text)

    def test_svg_geometry_and_accessibility(self):
        for box in ('0 0 0 10', '0 0 -1 10', '0 0 nan 10', '0 0 10'):
            text = SVG.format('').replace('0 0 10 10', box)
            with self.subTest(box=box), self.assertRaises(ValueError):
                checks.check_svg(text)
        for text in (SVG.format('').replace('Diagram', ''), '<!DOCTYPE svg>' + SVG.format('')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                checks.check_svg(text)

class RepositoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.write('README.md', '# Project\n')

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def errors(self):
        return checks.run_checks(self.root)[0]

    def test_ignored_private_files_are_not_read_but_tracked_ones_fail(self):
        self.write('.gitignore', 'secrets.yaml\n.esphome/\n')
        self.write('secrets.yaml', 'invalid: [')
        self.write('.esphome/generated.md', '[Broken](absent.md)')
        self.assertEqual(self.errors(), [])
        subprocess.run(['git', 'add', '-f', 'secrets.yaml'], cwd=self.root, check=True)
        self.assertTrue(any('secrets.yaml' in error for error in self.errors()))

    def test_new_untracked_source_is_checked(self):
        self.write('new.yaml', 'key: one\nkey: two\n')
        self.assertTrue(self.errors())

    def test_symlink_directory_is_rejected(self):
        (self.root / 'linked').symlink_to(self.root.parent, target_is_directory=True)
        self.assertTrue(any('linked' in error for error in self.errors()))

    def test_missing_private_and_external_file_links_fail(self):
        self.write('.gitignore', 'private.md\n')
        self.write('private.md', '# Private\n')
        for target in ('absent.md', 'private.md', '../outside.md', '#absent'):
            with self.subTest(target=target):
                self.write('README.md', f'# Project\n[Broken]({target})\n')
                self.assertTrue(self.errors())

    def test_reference_encoded_and_duplicate_heading_links(self):
        self.write('with space.md', '# Reset and startup\n## Step\n## Step\n')
        self.write('README.md', '[Details][guide]\n\n[guide]: with%20space.md#step-1\n')
        self.assertEqual(self.errors(), [])

    def test_fenced_link_examples_are_not_followed(self):
        self.write('README.md', '```markdown\n[Example](not-real.md)\n```\n')
        self.assertEqual(self.errors(), [])

    def test_invalid_encoding_reports_failure(self):
        (self.root / 'invalid.md').write_bytes(bytes([255, 254]))
        self.assertTrue(self.errors())

if __name__ == '__main__':
    unittest.main()
