"""Offline checks for the canonical Sun Bridge package and command interface."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class BrandingTests(unittest.TestCase):
    def command(self, module, *arguments):
        return subprocess.run(
            [sys.executable, "-B", "-m", module, *arguments],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )

    def test_project_has_one_canonical_implementation_package(self):
        from sunbridge import __version__
        from sunbridge.__main__ import main

        packages = {path.parent.name for path in ROOT.glob("*/__init__.py")}
        self.assertEqual(packages, {"sunbridge"})
        self.assertEqual(main.__module__, "sunbridge.__main__")
        metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('packages = ["sunbridge"]', metadata)
        self.assertIn('name = "sun-bridge"', metadata)
        self.assertIn(f'version = "{__version__}"', metadata)
        self.assertEqual(__version__, "0.3.0")

    def test_canonical_module_command_shows_help(self):
        result = self.command("sunbridge", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("demo", "validate", "pipedrive-import", "analyze", "setup", "doctor", "run"):
            self.assertIn(command, result.stdout)
        self.assertEqual(result.stderr, "")

    def test_canonical_module_validates_profiles(self):
        result = self.command("sunbridge", "validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated", result.stdout)
        self.assertIn("profiles", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_schema_identifier_uses_canonical_namespace(self):
        schema = json.loads((ROOT / "schemas/ahj-profile.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], "urn:sun-bridge:ahj-profile:v1")


if __name__ == "__main__":
    unittest.main()
