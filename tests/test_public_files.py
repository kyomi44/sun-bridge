"""Synthetic Git-index privacy checks; no private workspace data is read."""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_public_files as checker


class PublicIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")

    def git(self, *args, data=None):
        return subprocess.run(["git", *args], cwd=self.root, input=data,
                              capture_output=True, check=True).stdout

    def stage(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        self.git("add", "--", name)
        return path

    def synthetic_token(self):
        return "ghp_" + "a" * 24

    def test_staged_secret_is_found_after_worktree_is_cleaned(self):
        path = self.stage("sample.txt", self.synthetic_token())
        path.write_text("clean working copy")
        count, findings = checker.check_index(self.root)
        self.assertEqual(count, 1)
        self.assertIn(("sample.txt", "GitHub token"), findings)

    def test_unstaged_secret_does_not_replace_clean_index_content(self):
        path = self.stage("sample.txt", "clean staged copy")
        path.write_text(self.synthetic_token())
        self.assertEqual(checker.check_index(self.root), (1, []))

    def test_git_replace_cannot_hide_the_actual_staged_blob(self):
        self.stage("sample.txt", self.synthetic_token())
        staged = self.git("rev-parse", ":sample.txt").strip().decode()
        clean = self.git("hash-object", "-w", "--stdin", data=b"clean replacement").strip().decode()
        self.git("replace", staged, clean)
        _, findings = checker.check_index(self.root)
        self.assertIn(("sample.txt", "GitHub token"), findings)

    def test_missing_worktree_copy_still_checks_staged_blob(self):
        path = self.stage("sample.txt", "clean staged copy")
        path.unlink()
        self.assertEqual(checker.check_index(self.root), (1, []))

    def test_index_symlink_is_rejected_even_after_regular_replacement(self):
        path = self.root / "link.txt"
        path.symlink_to("safe-target")
        self.git("add", "--", "link.txt")
        path.unlink()
        path.write_text("regular working copy")
        _, findings = checker.check_index(self.root)
        self.assertTrue(any("symbolic link" in label for _, label in findings))

    def test_worktree_symlink_does_not_change_regular_index_mode(self):
        path = self.stage("sample.txt", "clean staged copy")
        path.unlink()
        path.symlink_to("missing-target")
        self.assertEqual(checker.check_index(self.root), (1, []))

    def test_unmerged_index_entries_are_rejected(self):
        first = self.git("hash-object", "-w", "--stdin", data=b"one").strip().decode()
        second = self.git("hash-object", "-w", "--stdin", data=b"two").strip().decode()
        entries = f"100644 {first} 1\tconflict.txt\n100644 {second} 2\tconflict.txt\n"
        self.git("update-index", "--index-info", data=entries.encode())
        self.assertEqual(checker.check_index(self.root), (1, [("conflict.txt", "unmerged Git index entry")]))

    def test_gitlink_is_rejected(self):
        tree = self.git("hash-object", "-t", "tree", "-w", "--stdin", data=b"").strip().decode()
        commit = self.git("-c", "user.name=Synthetic Test", "-c", "user.email=test@example.test",
                          "commit-tree", tree, "-m", "Synthetic test").strip().decode()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{commit},vendor")
        _, findings = checker.check_index(self.root)
        self.assertTrue(any("gitlink" in label for _, label in findings))

    def test_missing_staged_object_fails_closed(self):
        missing = "f" * 40
        self.git("update-index", "--add", "--info-only", "--cacheinfo", f"100644,{missing},missing.txt")
        _, findings = checker.check_index(self.root)
        self.assertTrue(any("missing or invalid staged blob" == label for _, label in findings))

    def test_executable_blob_is_supported(self):
        oid = self.git("hash-object", "-w", "--stdin", data=b"#!/bin/sh\nexit 0\n").strip().decode()
        self.git("update-index", "--add", "--cacheinfo", f"100755,{oid},run.sh")
        self.assertEqual(checker.check_index(self.root), (1, []))

    def test_binary_large_and_private_paths_are_rejected(self):
        self.stage("binary.bin", b"\x00binary")
        self.stage("large.txt", b"a" * (checker.MAX_FILE_BYTES + 1))
        self.stage("private/synthetic.json", "synthetic fixture only")
        self.stage("mail.zip", "synthetic fixture only")
        self.stage(".env", "synthetic fixture only")
        count, findings = checker.check_index(self.root)
        self.assertEqual(count, 5)
        self.assertEqual(len(findings), 5)

    def test_nested_project_cannot_inspect_parent_repository(self):
        self.stage("sample.txt", "clean staged copy")
        nested = self.root / "nested"
        nested.mkdir()
        count, findings = checker.check_index(nested)
        self.assertEqual(count, 0)
        self.assertTrue(any("isolated repository" in label for _, label in findings))

    def test_diagnostics_hide_secret_values_and_escape_filename_controls(self):
        token = self.synthetic_token()
        self.stage(token + ".txt", token)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(checker, "ROOT", self.root), patch("sys.argv", ["check", "--tracked"]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = checker.main()
        self.assertEqual(result, 1)
        self.assertNotIn(token, stdout.getvalue() + stderr.getvalue())
        self.assertIn("redacted filename", stderr.getvalue())
        self.assertNotIn("\n", checker._safe_name("a\nb.txt"))

    def test_git_error_output_is_never_printed(self):
        token = self.synthetic_token()
        result = subprocess.CompletedProcess(["git"], 1, stdout=b"", stderr=token.encode())
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(checker, "ROOT", self.root), patch.object(checker, "_git", return_value=result), patch("sys.argv", ["check", "--tracked"]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(checker.main(), 1)
        self.assertNotIn(token, stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
