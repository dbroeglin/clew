"""Import-bundle inspection and retained-source snapshots."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from formats import ImportedSource, Snapshot
from ingest_io import contained, fingerprint, no_redirect, require, sha256
from markdown_source import MarkdownSource


@dataclass
class Bundle:
    root: Path
    metadata: dict
    files: dict[str, str]
    markdown: MarkdownSource
    fingerprint: str

    def inventory(self) -> dict:
        return {
            "bundle": str(self.root), "fingerprint": self.fingerprint,
            "status": self.metadata["status"], "issues": self.metadata["issues"],
            "source": self.metadata["source"], "pages": self.metadata["pages"],
            "files": self.files, "line_count": len(self.markdown.lines),
            "safe_boundaries": self.markdown.boundaries,
            "page_markers": [{"line": index + 1, "page": number}
                             for index, number in self.markdown.markers.items()],
            "local_references": sorted({link.path for link in self.markdown.links}),
        }


def load_bundle(root: Path) -> Bundle:
    root = no_redirect(root)
    require(root.is_dir(), f"Not a bundle directory: {root}")
    manifest_bytes = contained(root, "manifest.json").read_bytes()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    require(isinstance(manifest, dict), "Manifest must be an object.")
    require(manifest.get("schema_version") == 3, "Expected import manifest version 3.")
    require(manifest.get("status") in {"extracted", "needs_review"},
            "Bundle is not a completed import.")
    require(manifest.get("document") == "document.md", "Expected document.md.")
    source = manifest.get("source")
    require(isinstance(source, dict), "Missing manifest source.")
    source = ImportedSource.model_validate(source).model_dump()
    path, name, digest, count = (source.get(key) for key in ("path", "name", "sha256", "page_count"))
    require(isinstance(name, str) and isinstance(path, str) and path == f"source/{name}",
            "Invalid retained source path/name.")
    require(name.lower().endswith(".pdf") and type(count) is int and count > 0,
            "Invalid PDF source metadata.")
    pdf_hash = sha256(contained(root, path))
    require(digest == pdf_hash, "Retained PDF hash differs from the manifest.")
    pages = manifest.get("pages")
    require(isinstance(pages, list) and bool(pages), "Missing imported page records.")
    numbers = []
    for page in pages:
        require(isinstance(page, dict), "Invalid page record.")
        number = page.get("number")
        require(type(number) is int and 1 <= number <= count, "Invalid source page number.")
        numbers.append(number)
        for field in ("raw_image", "raw_response"):
            require(isinstance(page.get(field), str), f"Missing page {field}.")
            contained(root, page[field])
    require(numbers == sorted(set(numbers)), "Imported pages must be unique and ordered.")
    issues = manifest.get("issues")
    require(isinstance(issues, list), "Import issues must be a list.")
    figures = manifest.get("figures")
    require(isinstance(figures, list), "Import figures must be a list.")
    declared: set[str] = set()
    for figure in figures:
        require(isinstance(figure, dict), "Invalid figure record.")
        if figure.get("asset") is not None:
            asset = figure["asset"]
            require(isinstance(asset, str) and asset.startswith("figures/"),
                    "Figure asset must be under figures/.")
            contained(root, asset)
            declared.add(asset)
    markdown_bytes = contained(root, "document.md").read_bytes()
    markdown = MarkdownSource(markdown_bytes.decode("utf-8"))
    require(list(markdown.markers.values()) == numbers,
            "Markdown page markers differ from imported page coverage.")
    references = {link.path for link in markdown.links}
    require(references <= declared | {path},
            f"Undeclared local references: {sorted(references - declared - {path})}")
    files = {reference: sha256(contained(root, reference))
             for reference in sorted({"document.md", path} | (references & declared))}
    require(files["document.md"] == hashlib.sha256(markdown_bytes).hexdigest()
            and files[path] == pdf_hash and sha256(root / "manifest.json") == manifest_hash,
            "Bundle changed during inspection.")
    metadata = {"status": manifest["status"], "source": source,
                "pages": numbers, "issues": issues}
    identity = fingerprint({"manifest": manifest_hash, "files": files})
    return Bundle(root, metadata, files, markdown, identity)


def load_snapshot(root: Path, record: dict) -> Bundle:
    record = Snapshot.model_validate(record).model_dump()
    require(isinstance(record, dict), "Invalid source snapshot.")
    require(set(record) == {"metadata", "files", "fingerprint"}, "Invalid snapshot fields.")
    metadata, files = record["metadata"], record["files"]
    require(isinstance(metadata, dict) and isinstance(files, dict), "Invalid snapshot metadata.")
    source = metadata.get("source")
    require(isinstance(source, dict) and isinstance(source.get("path"), str),
            "Invalid snapshot source.")
    require({"document.md", source["path"]} <= files.keys(), "Snapshot is missing source files.")
    for path, digest in files.items():
        require(isinstance(path, str) and isinstance(digest, str), "Invalid snapshot file.")
        require(sha256(contained(root, path)) == digest, f"Retained file changed: {path}")
    require(files[source["path"]] == source.get("sha256"), "Snapshot PDF identity differs.")
    require(source["path"] == f"source/{source['name']}", "Snapshot source path/name differs.")
    require(all(path in {"document.md", source["path"]} or path.startswith("figures/")
                for path in files), "Unexpected retained artifact.")
    markdown_bytes = contained(root, "document.md").read_bytes()
    require(hashlib.sha256(markdown_bytes).hexdigest() == files["document.md"],
            "Retained Markdown changed during validation.")
    markdown = MarkdownSource(markdown_bytes.decode("utf-8"))
    require(list(markdown.markers.values()) == metadata.get("pages"), "Snapshot page coverage differs.")
    require(metadata["pages"] == sorted(set(metadata["pages"]))
            and all(1 <= page <= source["page_count"] for page in metadata["pages"]),
            "Invalid retained page scope.")
    require({link.path for link in markdown.links} <= files.keys(), "Snapshot asset is missing.")
    return Bundle(root, metadata, files, markdown, record["fingerprint"])
