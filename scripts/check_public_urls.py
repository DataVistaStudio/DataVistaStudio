#!/usr/bin/env python3
"""Read-only public portfolio health check. No tokens, APIs, logins, or writes.

External links can fail transiently: the report concerns public reachability only,
not application health or authorization to access restricted systems.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"datavista.studio", "dvnews.datavista.studio", "market.961.menu", "961.menu", "meet.almayadeen.online"}
PAIR = re.compile(r'<a href="([^"]+)"><img src="([^"]+)"')
USER_AGENT = "DataVistaPublicPortfolioLinkAudit/1.0"


def approved_public_url(url):
    """Allow only known public HTTPS origins before any outbound request."""
    try:
        address = urlparse(url)
        return (
            address.scheme == "https"
            and address.hostname in ALLOWED
            and address.port in (None, 443)
            and address.username is None
            and address.password is None
        )
    except ValueError:
        return False


class ApprovedRedirects(HTTPRedirectHandler):
    """Refuse an off-domain redirect *before* urllib contacts its destination."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not approved_public_url(newurl):
            raise ValueError("redirect rejected: non-allowlisted public destination")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


OPENER = build_opener(ApprovedRedirects())


def read_pairs(filename):
    return PAIR.findall((ROOT / filename).read_text(encoding="utf-8"))


def check_one(url, image=False):
    if not approved_public_url(url):
        return (url, "blocked: URL is not an allowlisted public HTTPS origin")
    for attempt in range(2):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
            with OPENER.open(request, timeout=10) as response:
                if response.status != 200:
                    return (url, f"HTTP {response.status}")
                final = urlparse(response.geturl())
                if final.scheme != "https" or final.hostname not in ALLOWED:
                    return (url, "redirect left approved public domains")
                if image:
                    if response.headers.get("content-type", "").split(";")[0].lower() not in {"image/jpeg", "image/png", "image/webp"}:
                        return (url, "unexpected image content-type")
                    if response.headers.get("content-length") == "0":
                        return (url, "empty image response")
            return (url, None)
        except HTTPError as error:
            if error.code in (404, 405) and not image:
                # Some public sites handle GET correctly but do not implement HEAD.
                # Verify the real user-facing page instead of a false 404 alarm.
                try:
                    req = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
                    with OPENER.open(req, timeout=10) as res:
                        final = urlparse(res.geturl())
                        if res.status == 200 and res.read(1) and final.scheme == "https" and final.hostname in ALLOWED:
                            return (url, None)
                except Exception as nested:
                    if attempt:
                        return (url, type(nested).__name__)
            elif attempt:
                return (url, f"HTTP {error.code}")
        except Exception as error:
            if attempt:
                return (url, type(error).__name__)
        time.sleep(0.5)
    return (url, "two attempts failed")


def main():
    expected = {
        "portfolio/README.md": 16,
        "portfolio/observatories.md": 11,
    }
    documents = {name: read_pairs(name) for name in expected}
    issues = []
    for name, pairs in documents.items():
        if len(pairs) != expected[name]:
            issues.append((name, f"unexpected project count {len(pairs)} != {expected[name]}"))
    jobs = {}
    for pairs in documents.values():
        for destination, picture in pairs:
            jobs[destination] = False
            if picture.startswith("https://"):
                jobs[picture] = True
            else:
                # Relative SVG cards are verified by the existing offline integrity job.
                if not picture.startswith("../media/cards/") or not (ROOT / "portfolio" / picture).resolve().is_file():
                    issues.append((picture, "local art is missing"))
    if len(jobs) != 48:
        issues.append(("portfolio", f"expected 48 distinct public URLs, got {len(jobs)}"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(check_one, url, is_image): url for url, is_image in jobs.items()}
        for future in as_completed(futures):
            url, error = future.result()
            if error:
                issues.append((url, error))
    print(f"PUBLIC_PORTFOLIO_CHECK checked={len(jobs)} issues={len(issues)}")
    for url, error in sorted(issues):
        print(f"FAIL | {url} | {error}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
