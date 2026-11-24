"""Regression tests for strict live Pages checks and retry-safe artifacts."""
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
import smoke_pages

URL = "https://dancyuser.github.io/wine-atlas/README.md"

def http(code):
    return urllib.error.HTTPError(URL, code, "test", {}, None)

class SmokePagesTests(unittest.TestCase):
    @patch("smoke_pages.time.sleep")
    @patch("smoke_pages.fetch")
    def test_transient_error_then_confirmed_absence(self, fetch, sleep):
        fetch.side_effect = [http(503), http(404)]
        smoke_pages.check_forbidden(URL)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(sleep.call_count, 1)
        for call in fetch.call_args_list:
            self.assertEqual(urlsplit(call.args[0]).path, urlsplit(URL).path)
            self.assertIn("pages-smoke=", urlsplit(call.args[0]).query)

    @patch("smoke_pages.time.sleep")
    @patch("smoke_pages.fetch", side_effect=http(503))
    def test_persistent_503_is_not_success(self, fetch, sleep):
        with self.assertRaisesRegex(ValueError, "503"):
            smoke_pages.check_forbidden(URL)
        self.assertEqual(fetch.call_count, 4)

    @patch("smoke_pages.fetch", return_value=b"unexpected content")
    def test_public_internal_file_fails(self, fetch):
        with self.assertRaisesRegex(ValueError, "publicly accessible"):
            smoke_pages.check_forbidden(URL)

    @patch("smoke_pages.fetch", side_effect=http(403))
    def test_forbidden_is_valid(self, fetch):
        smoke_pages.check_forbidden(URL)
        self.assertEqual(fetch.call_count, 1)

    def test_archived_simplewine_rows_not_required_in_live_dom(self):
        rows = [
            {"id": "sw-1", "year": 2024},
            {"id": "sw-2", "year": 2023, "publication_review": {"status": "excluded"}},
            {"id": "sw-3", "year": 2022, "availability": {"status": "out_of_stock"}},
            {"id": "sw-4", "year": 2022},
            {"id": "sw-5", "year": None},
        ]
        self.assertEqual(smoke_pages.published_ids(rows, {"sw-4"}), {"sw-1"})

    def test_upload_and_deploy_select_same_attempt_specific_artifact(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pages.yml").read_text()
        name = "github-pages-${{ github.run_id }}-${{ github.run_attempt }}"
        self.assertIn("name: " + name, workflow)
        self.assertIn("artifact_name: " + name, workflow)

if __name__ == "__main__":
    unittest.main()
