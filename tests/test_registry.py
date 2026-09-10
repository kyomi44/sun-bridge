"""Capability claims must point to implementation and tests, not just a name."""
import copy
import json
import unittest
from unittest.mock import patch

from permitkit.registry import integration_registry


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = integration_registry()

    def validate(self, value):
        with patch("pathlib.Path.read_text", return_value=json.dumps(value)):
            return integration_registry()

    def test_rejects_invalid_topology_and_implicit_claims(self):
        for value in ([], {}, {"schema_version": True, "crms": []}, {"schema_version": 1, "crms": []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(value)

    def test_available_claim_needs_nonempty_source_and_tests(self):
        for key in ("implementation", "tests"):
            value = copy.deepcopy(self.registry)
            value["crms"][0][key] = []
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(value)

    def test_planned_claim_cannot_advertise_reads_or_writes(self):
        for key in ("organization_discovery", "permit_reads", "crm_writes"):
            value = copy.deepcopy(self.registry)
            value["crms"][2][key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(value)

    def test_rejects_duplicate_missing_and_malformed_references(self):
        mutations = [
            ("id", self.registry["crms"][1]["id"]), ("id", ""), ("scope", ""),
            ("permit_reads", "true"), ("implementation", "permitkit/crm.py"),
            ("implementation", ["../private/hidden.py"]), ("tests", ["tests/does-not-exist.py"]),
        ]
        for key, replacement in mutations:
            value = copy.deepcopy(self.registry)
            value["crms"][0][key] = replacement
            with self.subTest(key=key, replacement=replacement), self.assertRaises(ValueError):
                self.validate(value)


if __name__ == "__main__":
    unittest.main()
