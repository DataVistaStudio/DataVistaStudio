#!/usr/bin/env python3
"""Offline integrity check for the public DataVista Studio GitHub portfolio.

No network access, credentials, third-party packages or production deployment.
"""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT_GALLERIES = [
    ROOT / "portfolio" / "README.md",
    ROOT / "portfolio" / "README.ar.md",
    ROOT / "portfolio" / "visual-tour.md",
]
OBSERVATORIES = ROOT / "portfolio" / "observatories.md"
MD_LINKS = re.compile(r"\[[^\]]+\]\(([^)\s]+)(?:\s+\"[^\"]+\")?\)")
HTML_LINKS = re.compile(r"""(?:src|href)=["']([^"']+)["']""")
IMG = re.compile(r"""<img\b[^>]*\bsrc=["']([^"']+)["']""", re.I)
EXPECTED_JPGS = {
    "newsroom", "market-961-menu", "people-report", "experts2",
    "cr-multiview", "satr-academy", "ebook", "stock", "961-menu", "talk",
}
EXPECTED_SVGS = {
    "observatories", "flashnews", "economy-desk",
    "news-map", "aparat", "jobvista",
}
EXPECTED_OBS = {
    "general", "usa", "arab", "russia", "iran", "pakistan",
    "hebrew", "lebanon", "iraq", "africa", "agencies",
}
ART_PREFIX = "https://datavista.studio/assets/portfolio-20261122/cards/"
OBS_PREFIX = "https://datavista.studio/assets/portfolio-20261122/observatories/"
errors = []


def check_images(doc, jpg_count, svg_count, obs_count=0):
    content = doc.read_text(encoding="utf-8")
    image_urls = IMG.findall(content)
    jpg = set()
    svg = set()
    obs = set()
    for image in image_urls:
        if image.startswith(ART_PREFIX) and image.endswith(".jpg"):
            jpg.add(image[len(ART_PREFIX):-4])
        elif image.startswith("../media/cards/") and image.endswith(".svg"):
            svg.add(image[len("../media/cards/"):-4])
        elif image.startswith(OBS_PREFIX) and image.endswith(".webp"):
            obs.add(image[len(OBS_PREFIX):-5])
    if len(jpg) != jpg_count or len(svg) != svg_count or len(obs) != obs_count:
        errors.append(f"{doc.relative_to(ROOT)}: image counts jpg={len(jpg)}, svg={len(svg)}, obs={len(obs)}; expected {jpg_count}/{svg_count}/{obs_count}")
    if jpg_count == 10 and jpg != EXPECTED_JPGS:
        errors.append(f"{doc.relative_to(ROOT)}: project jpg names inconsistent")
    if svg_count == 6 and svg != EXPECTED_SVGS:
        errors.append(f"{doc.relative_to(ROOT)}: local SVG project names inconsistent")
    if obs_count == 11 and obs != EXPECTED_OBS:
        errors.append(f"{doc.relative_to(ROOT)}: observatory names inconsistent")
    if len(image_urls) != jpg_count + svg_count + obs_count:
        errors.append(f"{doc.relative_to(ROOT)}: unexpected extra or duplicate project images")


def check_local_links(doc):
    content = doc.read_text(encoding="utf-8")
    rel = doc.relative_to(ROOT)
    for raw in MD_LINKS.findall(content) + HTML_LINKS.findall(content):
        if raw.startswith(("#", "mailto:", "tel:")):
            continue
        parsed = urlsplit(raw)
        if parsed.scheme in ("http", "https"):
            if not parsed.netloc:
                errors.append(f"{rel}: malformed web link")
            continue
        if parsed.scheme or raw.startswith("//"):
            errors.append(f"{rel}: unexpected link scheme")
            continue
        target = unquote(parsed.path)
        if not target:
            continue
        dest = (doc.parent / target).resolve()
        if not dest.is_relative_to(ROOT.resolve()) or not dest.is_file():
            errors.append(f"{rel}: broken local link: {raw}")
    if "github.com/ZoroTV" in content:
        errors.append(f"{rel}: old founder username link")
    if "DataVista Marketplace" in content:
        errors.append(f"{rel}: outdated public marketplace name")


def main():
    for doc in sorted(ROOT.rglob("*.md")):
        check_local_links(doc)
    for doc in PROJECT_GALLERIES:
        check_images(doc, 10, 6)
        if "Market.961.MENU" not in doc.read_text(encoding="utf-8"):
            errors.append(f"{doc.relative_to(ROOT)}: current market name missing")
    check_images(OBSERVATORIES, 0, 0, 11)
    for path in [ROOT / "README.md", ROOT / "README.ar.md"]:
        check_images(path, 6, 0)
    if errors:
        print("PORTFOLIO_FAIL", len(errors))
        for err in errors:
            print("-", err)
        return 1
    print("PORTFOLIO_PASS | 16 projects (10 art JPG + 6 local SVG) | 11 observatories | local links valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
