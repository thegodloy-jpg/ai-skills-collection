"""Exercise local installation in temporary directories only."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def run_installer(self, destination, *selection):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "install.py"),
             *selection, "--dest", str(destination)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )

    def test_dependency_is_installed_once(self):
        for names in (("grill-me",), ("grill-me", "grilling")):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / "skills"
                result = self.run_installer(destination, "--skills", *names)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual({path.name for path in destination.iterdir()}, {"grill-me", "grilling"})
                self.assertTrue((destination / "grilling" / "SKILL.md").is_file())

    def test_existing_target_stops_batch_without_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            existing = destination / "grill-me"
            existing.mkdir(parents=True)
            marker = existing / "keep.txt"
            marker.write_text("keep existing content", encoding="utf-8")
            result = self.run_installer(destination, "--skills", "grill-me")
            self.assertEqual(result.returncode, 1)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(list(destination.iterdir()), [existing])
            self.assertEqual(list(existing.iterdir()), [marker])
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep existing content")

    def test_official_install_entry_is_not_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            result = self.run_installer(destination, "--skills", "grill-me", "sites:sites")
            self.assertEqual(result.returncode, 1)
            self.assertIn("requires official installation", result.stderr)
            self.assertFalse(destination.exists())

    def test_all_installs_exactly_bundled_entries(self):
        catalog = json.loads((REPO_ROOT / "catalog.json").read_text(encoding="utf-8-sig"))
        expected = {entry["name"] for entry in catalog["skills"] if entry["distribution"] == "bundled"}
        self.assertEqual(len(expected), 23)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            result = self.run_installer(destination, "--all")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({path.name for path in destination.iterdir()}, expected)
            self.assertTrue(all((destination / name / "SKILL.md").is_file() for name in expected))


if __name__ == "__main__":
    unittest.main()
