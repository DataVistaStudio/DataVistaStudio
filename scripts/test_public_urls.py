#!/usr/bin/env python3
"""Offline regression tests for the public portfolio link probe; no web requests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_public_urls as health


class FakeResponse:
    status = 200
    headers = {"content-type": "text/html"}

    def __init__(self, url):
        self.url = url

    def geturl(self):
        return self.url

    def read(self, amount=1):
        return b"x"

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class ApprovedOriginTests(unittest.TestCase):
    def test_allowed_public_sites(self):
        for url in (
            "https://datavista.studio/newsroom/",
            "https://datavista.studio:443/insights/",
            "https://dvnews.datavista.studio/dvwp/",
            "https://market.961.menu/",
            "https://961.menu/",
            "https://meet.almayadeen.online/",
        ):
            with self.subTest(url=url):
                self.assertTrue(health.approved_public_url(url))

    def test_unapproved_sites_are_rejected(self):
        for url in (
            "http://datavista.studio/",
            "https://evil.example.com/",
            "https://datavista.studio.evil.example.com/",
            "https://127.0.0.1/",
            "https://localhost/",
            "https://datavista.studio:444/",
            "https://user:password@datavista.studio/",
            "ftp://datavista.studio/",
            "https://[invalid",
        ):
            with self.subTest(url=url):
                self.assertFalse(health.approved_public_url(url))

    def test_reject_redirect_without_requesting_destination(self):
        handler = health.ApprovedRedirects()
        original = Request("https://datavista.studio/newsroom/", method="HEAD")
        for target in (
            "http://127.0.0.1/secrets",
            "https://evil.example.com/",
            "https://datavista.studio.evil.example.com/",
            "https://datavista.studio:444/",
        ):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    handler.redirect_request(original, None, 302, "Found", {}, target)

    def test_allow_known_public_redirect(self):
        handler = health.ApprovedRedirects()
        original = Request("https://datavista.studio/insights/", method="HEAD")
        redirected = handler.redirect_request(
            original, None, 302, "Found", {},
            "https://dvnews.datavista.studio/dvwp/"
        )
        self.assertEqual(redirected.full_url, "https://dvnews.datavista.studio/dvwp/")

    def test_invalid_host_never_contacts_network(self):
        with patch.object(health.OPENER, "open") as mocked:
            url, reason = health.check_one("https://evil.example.com/", image=False)
        mocked.assert_not_called()
        self.assertEqual(url, "https://evil.example.com/")
        self.assertIn("blocked", reason)

    def test_html_head_404_falls_back_to_real_get(self):
        url = "https://datavista.studio/insights/general?lang=ar"
        fail = HTTPError(url, 404, "HEAD is not implemented", {}, None)
        with patch.object(
            health.OPENER, "open",
            side_effect=[fail, FakeResponse(url)],
        ) as mocked:
            value, problem = health.check_one(url, image=False)
        self.assertEqual(value, url)
        self.assertIsNone(problem)
        self.assertEqual(mocked.call_count, 2)

    def test_disallowed_redirect_reports_failure(self):
        url = "https://datavista.studio/newsroom/"
        with patch.object(
            health.OPENER, "open",
            side_effect=ValueError("redirect rejected"),
        ):
            value, problem = health.check_one(url, image=False)
        self.assertEqual(value, url)
        self.assertIsNotNone(problem)


if __name__ == "__main__":
    unittest.main()
