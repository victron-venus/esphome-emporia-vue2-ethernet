"""Reject partial dependency updates before checks or firmware validation run."""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def pins(path):
    return {
        name.lower().replace('_', '-'): version
        for name, version in re.findall(r'^([\w.-]+)==([^\s\\]+)', path.read_text(), re.M)
    }


class DependencyContracts(unittest.TestCase):
    def test_documentation_input_pins_match_hashed_install_lock(self):
        source = pins(ROOT / 'requirements-checks.in')
        locked = pins(ROOT / 'requirements-checks.txt')
        self.assertTrue(source)
        self.assertEqual({name: locked.get(name) for name in source}, source)
        self.assertIn('--hash=sha256:', (ROOT / 'requirements-checks.txt').read_text())

    def test_firmware_image_matches_local_install_version(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/validate.yml').read_text())
        image = workflow['jobs']['firmware-build']['container']['image']
        expected = pins(ROOT / 'firmware/requirements.txt')['esphome']
        self.assertRegex(image, rf'^ghcr\.io/esphome/esphome:{re.escape(expected)}@sha256:[0-9a-f]{{64}}$')
