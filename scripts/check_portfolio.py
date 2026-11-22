#!/usr/bin/env python3
"""Offline integrity check for the public DataVista Studio GitHub portfolio.

No network access, credentials, third-party packages or production deployment.
"""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import re
import sys
import os
import hashlib
import xml.etree.ElementTree as ET

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
    avatar_count = 1 if doc.parent == ROOT and doc.name in ("README.md", "README.ar.md") else 0
    if avatar_count and not any(img.startswith("https://avatars.githubusercontent.com/u/253784265") for img in image_urls):
        errors.append(f"{doc.relative_to(ROOT)}: company avatar missing")
    if len(image_urls) != jpg_count + svg_count + obs_count + avatar_count:
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



def check_vector_artwork():
    """Validate the six finished project-specific SVGs using only Python stdlib."""
    fingerprints = set()
    for slug in sorted(EXPECTED_SVGS):
        path = ROOT / "media" / "cards" / (slug + ".svg")
        if not path.is_file():
            errors.append(f"missing art: {path.relative_to(ROOT)}")
            continue
        blob = path.read_bytes()
        if len(blob) < 3500:
            errors.append(f"artwork too small: {slug}")
        fingerprints.add(hashlib.sha256(blob).hexdigest())
        try:
            svg = ET.fromstring(blob)
        except ET.ParseError as err:
            errors.append(f"invalid SVG XML: {slug}: {err}")
            continue
        ns = "{http://www.w3.org/2000/svg}"
        if svg.tag != ns + "svg" or svg.get("viewBox") != "0 0 1440 810":
            errors.append(f"artwork does not use canonical 16:9 canvas: {slug}")
        if svg.get("role") != "img" or not svg.get("aria-labelledby"):
            errors.append(f"missing SVG accessibility semantics: {slug}")
        title = svg.find(ns + "title")
        desc = svg.find(ns + "desc")
        if title is None or desc is None or not (title.text or "").strip() or not (desc.text or "").strip():
            errors.append(f"missing SVG title / description: {slug}")
        # Keep GitHub-rendered project art inert: no active content or remote fetches.
        if b"<!doctype" in blob.lower() or b"<!entity" in blob.lower():
            errors.append(f"DTD / entity content is forbidden in art: {slug}")
        forbidden_elements = {"script", "foreignObject", "image", "iframe", "audio", "video", "animate", "set"}
        for node in svg.iter():
            local = node.tag.rsplit("}", 1)[-1]
            if local in forbidden_elements:
                errors.append(f"unsafe SVG element {local}: {slug}")
            for attr, value in node.attrib.items():
                key = attr.rsplit("}", 1)[-1].lower()
                if key.startswith("on") or key == "href":
                    errors.append(f"forbidden SVG event/link attribute {key}: {slug}")
                if re.search(r"url\\s*\\(\\s*['\\\"]?\\s*(?:https?:|javascript:|data:|//)", value, re.I):
                    errors.append(f"external SVG paint/resource URL: {slug}")

        if len([node for node in svg.iter() if node.tag in (ns + "path", ns + "rect", ns + "circle")]) < 10:
            errors.append(f"insufficient project-specific vector composition: {slug}")
    if len(fingerprints) != len(EXPECTED_SVGS):
        errors.append("vector artwork duplicates detected")

def main():
    # Protect against accidentally running this workflow against another account/repository.
    for var, expected in (
        ("GITHUB_REPOSITORY", "DataVistaStudio/DataVistaStudio"),
        ("GITHUB_REPOSITORY_ID", "1467093337"),
        ("GITHUB_REPOSITORY_OWNER_ID", "253784265"),
    ):
        actual = os.environ.get(var)
        if actual and actual != expected:
            errors.append(f"wrong GitHub target: {var}={actual}, expected {expected}")
    for doc in sorted(ROOT.rglob("*.md")):
        check_local_links(doc)
    for doc in PROJECT_GALLERIES:
        check_images(doc, 10, 6)
        if "Market.961.MENU" not in doc.read_text(encoding="utf-8"):
            errors.append(f"{doc.relative_to(ROOT)}: current market name missing")
    check_images(OBSERVATORIES, 0, 0, 11)
    check_vector_artwork()
    for path in [ROOT / "README.md", ROOT / "README.ar.md"]:
        check_images(path, 6, 0)
    if errors:
        print("PORTFOLIO_FAIL", len(errors))
        for err in errors:
            print("-", err)
        return 1
    print("PORTFOLIO_PASS | 16 distinct project artworks (10 JPG + 6 accessible SVG) | 11 observatories | local links valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
