"""Verify Pages exposes only the deliberate static allowlist."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_site import ROOT, PUBLIC, build_site


class SitePackageTests(unittest.TestCase):
    def test_allowlisted_file_contents_and_no_archives(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "_site"
            self.assertEqual(build_site(output), len(PUBLIC))
            files = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
            self.assertEqual(files, set(PUBLIC) | {".nojekyll"})
            for relative in PUBLIC:
                self.assertEqual(
                    hashlib.sha256((ROOT / relative).read_bytes()).digest(),
                    hashlib.sha256((output / relative).read_bytes()).digest()
                )
            self.assertNotIn("README.md", files)
            self.assertFalse(any(x.startswith("scripts/") or x.startswith("data/archive/")
                                 or x.startswith(".github/") or x.startswith(".git/")
                                 for x in files))

    def test_no_repository_overwrite(self):
        with self.assertRaises(ValueError):
            build_site(ROOT)


if __name__ == "__main__":
    unittest.main()
