"""Offline command compatibility checks for Sun Bridge and its older aliases."""

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

    def test_solarbridge_delegates_to_existing_main(self):
        from permitkit.__main__ import main as legacy_main
        from solarbridge.__main__ import main as canonical_main
        from sunbridge.__main__ import main as sun_main

        self.assertIs(canonical_main, legacy_main)
        self.assertIs(sun_main, legacy_main)

    def test_both_module_commands_show_help(self):
        for module in ("sunbridge", "solarbridge", "permitkit"):
            with self.subTest(module=module):
                result = self.command(module, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("demo", result.stdout)
                self.assertIn("validate", result.stdout)
                self.assertIn("pipedrive-import", result.stdout)
                self.assertEqual(result.stderr, "")

    def test_both_module_commands_validate_the_same_profiles(self):
        results = [self.command(module, "validate") for module in ("sunbridge", "solarbridge", "permitkit")]
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Validated", result.stdout)
            self.assertIn("training outcomes", result.stdout)
        self.assertEqual(results[0].stdout, results[1].stdout)
        self.assertEqual(results[0].stdout, results[2].stdout)

    def test_schema_identifier_remains_backwards_compatible(self):
        schema = json.loads((ROOT / "schemas/ahj-profile.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], "urn:open-permit-kit:ahj-profile:v1")


if __name__ == "__main__":
    unittest.main()
