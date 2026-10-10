"""Inspect completed conversion bundles without importing the cloud converter."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pymupdf

from document_io import contained, digest, fingerprint, no_redirect, read_json, require, sha256
from markdown_source import MarkdownSource


def pdf_pages(path: Path) -> int:
    try:
        with pymupdf.open(no_redirect(path)) as pdf:
            require(pdf.is_pdf and not pdf.needs_pass, f"Not an unlocked PDF: {path}")
            require(len(pdf) > 0, f"Empty PDF: {path}")
            return len(pdf)
    except pymupdf.FileDataError as error:
        raise ValueError(f"Invalid retained PDF: {path}: {error}") from error


@dataclass
class Bundle:
    root: Path
    manifest: dict
    markdown: MarkdownSource
    files: dict[str, str]
    fingerprint: str

    @property
    def source(self) -> dict:
        return self.manifest["source"]

    @property
    def pages(self) -> list[int]:
        return [page["number"] for page in self.manifest["pages"]]

    def inventory(self) -> dict:
        return {"bundle": str(self.root), "fingerprint": self.fingerprint,
                "source": self.source, "status": self.manifest["status"],
                "issues": self.manifest["issues"], "files": self.files,
                **self.markdown.inventory()}


def load_bundle(root: Path) -> Bundle:
    root = no_redirect(root)
    require(root.is_dir(), f"Not a conversion bundle: {root}")
    manifest_path = contained(root, "manifest.json")
    manifest_hash = sha256(manifest_path)
    manifest = read_json(manifest_path)
    require(isinstance(manifest, dict) and type(manifest.get("schema_version")) is int
            and manifest["schema_version"] == 3, "Expected conversion manifest version 3.")
    require(manifest.get("status") in {"extracted", "needs_review"},
            "Conversion bundle is incomplete.")
    require(manifest.get("document") == "document.md", "Expected converted document.md.")
    source = manifest.get("source")
    require(isinstance(source, dict) and isinstance(source.get("name"), str),
            "Missing conversion source metadata.")
    name = source["name"]
    require(Path(name).name == name and name.lower().endswith(".pdf")
            and source.get("path") == f"source/{name}", "Invalid retained PDF name/path.")
    pdf = contained(root, source["path"])
    require(sha256(pdf) == source.get("sha256"), "Retained PDF hash differs from the manifest.")
    count = pdf_pages(pdf)
    require(type(source.get("page_count")) is int and count == source["page_count"],
            "Retained PDF page count differs from the manifest.")
    pages = manifest.get("pages")
    require(isinstance(pages, list) and bool(pages), "Missing conversion page records.")
    numbers = []
    configuration = manifest.get("configuration", {})
    require(isinstance(configuration, dict), "Invalid conversion configuration metadata.")
    for page in pages:
        require(isinstance(page, dict) and type(page.get("number")) is int
                and 1 <= page["number"] <= count, "Invalid original PDF page number.")
        numbers.append(page["number"])
        for key in ("raw_image", "raw_response"):
            contained(root, page.get(key))
        if configuration.get("mathjax_version") is not None or page.get("raw_math") is not None:
            contained(root, page.get("raw_math"))
        review = page.get("review")
        require(not configuration.get("page_review") or review is not None,
                "Reviewed conversion is missing page review evidence.")
        if review is not None:
            require(isinstance(review, dict) and review.get("status") in {"passed", "needs_review"}
                    and isinstance(review.get("attempts"), list) and bool(review["attempts"]),
                    "Invalid page review record.")
            for attempt in review["attempts"]:
                require(isinstance(attempt, dict), "Invalid page review attempt.")
                for key in ("raw_markdown", "raw_response", "raw_review"):
                    contained(root, attempt.get(key))
                if configuration.get("mathjax_version") is not None or attempt.get("raw_math") is not None:
                    contained(root, attempt.get("raw_math"))
    require(numbers == sorted(set(numbers)), "Imported PDF pages must be ordered and unique.")
    require(isinstance(manifest.get("issues"), list), "Conversion issues must be a list.")
    figures = manifest.get("figures")
    require(isinstance(figures, list), "Conversion figures must be a list.")
    assets = set()
    for figure in figures:
        require(isinstance(figure, dict), "Invalid figure record.")
        if figure.get("asset") is not None:
            asset = figure["asset"]
            require(isinstance(asset, str) and asset.startswith("figures/"),
                    "Figure asset must be under figures/.")
            require(asset not in assets, f"Duplicate declared figure asset: {asset}")
            contained(root, asset)
            assets.add(asset)
    raw = contained(root, "document.md").read_bytes()
    markdown = MarkdownSource(raw.decode("utf-8"))
    require(bool(markdown.lines), "Converted Markdown is empty.")
    require(list(markdown.markers.values()) == numbers,
            "Parsed Markdown page markers differ from imported PDF coverage.")
    require(not any(token.type == "html_block" and any(marker in token.content
                    for marker in ("<!-- clew:", "<!-- /clew:")) for token in markdown.tokens),
            "Converted source contains reserved preparation markers.")
    references = set()
    for item in markdown.links:
        parsed = urlsplit(item.target)
        if parsed.scheme or item.target.startswith(("#", "//")):
            continue
        reference = unquote(parsed.path)
        if reference:
            require(reference in assets | {source["path"], "document.md"},
                    f"Undeclared local source reference at line {item.line}: {item.target}")
            references.add(reference)
    files = {reference: sha256(contained(root, reference))
             for reference in sorted({"document.md", source["path"]} | (references & assets))}
    require(files["document.md"] == digest(raw) and sha256(manifest_path) == manifest_hash,
            "Conversion bundle changed during inspection.")
    identity = fingerprint({"manifest": manifest_hash, "files": files})
    return Bundle(root, manifest, markdown, files, identity)
