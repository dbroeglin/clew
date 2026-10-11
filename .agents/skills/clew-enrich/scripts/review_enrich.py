"""Review scratch aid files or verify persisted files against an approved proposal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import yaml

from validate_enrich import EnrichError, inventory, local_path, require, sha256, validate


def review(root: Path, baseline: Path, directories: list[Path], proposal: Path) -> dict:
    root, baseline, proposal = local_path(root), local_path(baseline), local_path(proposal)
    require(proposal.suffix == ".md", "Proposal must be a Markdown file.")
    manifest = local_path(proposal.with_suffix(".json"))
    require(not proposal.is_relative_to(root), "Proposal must be outside the chapter.")
    require(proposal.parent.is_dir(), "Proposal parent must already exist.")
    require(not proposal.exists() and not manifest.exists(), "Proposal files already exist; choose new paths.")
    drafts: dict[str, bytes] = {}
    sources = {}
    destinations = set()
    for directory in directories:
        directory = local_path(directory)
        require(directory.is_dir() and not directory.is_relative_to(root),
                f"Draft directory must be outside the chapter: {directory}")
        require(not proposal.is_relative_to(directory), "Proposal must be outside draft directories.")
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() != ".md":
                continue
            require(not path.name.startswith("."), f"Hidden aid filename is unsupported: {path.name}")
            path = local_path(path)
            require(path.is_file(), f"Draft is not a regular file: {path}")
            relative = "aides/" + path.name
            require(relative.casefold() not in destinations, f"Duplicate draft destination: {relative}")
            destinations.add(relative.casefold())
            drafts[relative] = path.read_bytes()
            sources[relative] = str(path)
    require(bool(drafts), "No Markdown drafts found.")
    result = validate(root, baseline, drafts=drafts)
    details = result["aid_details"]
    details.sort(key=lambda row: row["path"])
    preview = [
        "# Enrich exact proposal", "",
        "Scratch review only: the chapter has not been edited. Approval must cover "
        "the exact files and prose below; this report is not an authorization.", "",
        f"New aids: {len(details)}. New hints: {result['new_hints']}. "
        f"New explanation sections: {result['new_explanations']}. "
        f"Explained aids: {result['new_aids_with_explanations']}. "
        f"Hints-only aids: {result['new_hint_only_aids']}.", "",
        "Questions without an aid (including existing aids in the coverage check): "
        + (", ".join(result["questions_without_aid"]) or "none") + ".", "",
        "Mechanical checks do not prove mathematical correctness, citation relevance, "
        "or instructional quality. Complete semantic review before requesting approval.", "",
    ]
    for row in details:
        row["source"] = sources[row["path"]]
        text = drafts[row["path"]].decode("utf-8-sig")
        fence = "`" * max(3, 1 + max((len(match[0]) for match in re.finditer(r"`+", text)), default=0))
        preview.extend([
            f"## {row['path']}", "",
            f"Question: {row['question']}",
            "Supplied answer: " + (row["correction"] or "none used for an explanation"),
            "Course mappings: " + ", ".join(row["course_links"]), "",
            fence + "markdown", text, fence, "",
        ])
    data = ("\n".join(preview) + "\n").encode("utf-8")
    result.update({
        "schema_version": 1, "status": "drafts-validated", "baseline_sha256": sha256(baseline.read_bytes()),
        "proposal_sha256": sha256(data), "check_scope": "scratch drafts over unchanged chapter",
    })
    encoded = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with proposal.open("xb") as stream:
        stream.write(data)
    with manifest.open("xb") as stream:
        stream.write(encoded)
    return {"status": result["status"], "proposal": str(proposal), "manifest": str(manifest),
            "aids": len(details), "questions_without_aid": result["questions_without_aid"],
            "new_hints": result["new_hints"], "new_explanations": result["new_explanations"],
            "new_aids_with_explanations": result["new_aids_with_explanations"],
            "new_hint_only_aids": result["new_hint_only_aids"],
            "proposal_sha256": result["proposal_sha256"], "manifest_sha256": sha256(encoded)}


def verify_approved(root: Path, baseline: Path, proposal: Path, manifest_sha256: str) -> dict:
    root, baseline, proposal = local_path(root), local_path(baseline), local_path(proposal)
    require(not proposal.is_relative_to(root), "Proposal must be outside the chapter.")
    manifest = local_path(proposal.with_suffix(".json"))
    manifest_bytes = manifest.read_bytes()
    require(sha256(manifest_bytes) == manifest_sha256, "Proposal manifest changed.")
    approved = json.loads(manifest_bytes.decode("utf-8-sig"))
    require(isinstance(approved, dict) and approved.get("schema_version") == 1
            and approved.get("status") == "drafts-validated" and approved.get("chapter") == str(root),
            "Invalid proposal manifest or different chapter.")
    require(sha256(proposal.read_bytes()) == approved.get("proposal_sha256"), "Proposal content changed.")
    require(sha256(baseline.read_bytes()) == approved.get("baseline_sha256"), "Original baseline changed.")
    details = approved.get("aid_details")
    require(isinstance(details, list) and bool(details), "Proposal manifest needs aid details.")
    expected = {}
    for row in details:
        require(isinstance(row, dict) and isinstance(row.get("path"), str)
                and isinstance(row.get("sha256"), str), "Invalid proposal aid detail.")
        require(row["path"] not in expected, f"Duplicate approved destination: {row['path']}")
        expected[row["path"]] = row["sha256"]
    result = validate(root, baseline)
    require(set(result["new_aids"]) == set(expected), "Persisted additions differ from the approved set.")
    current, directories = inventory(root)
    original_directories = set(json.loads(baseline.read_bytes())["directories"])
    require(set(directories) - original_directories == {"aides"} - original_directories,
            "Persisted directories differ from the approved set.")
    for relative, digest in expected.items():
        require(sha256(current[relative]) == digest, f"Persisted aid differs from approval: {relative}")
    result["approved_bytes_identical"] = True
    result["limitations"].append("Approval is a host/user decision, not something this checker can grant.")
    return result


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("chapter", type=Path)
    cli.add_argument("--before", type=Path, required=True, metavar="BASELINE")
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--drafts", type=Path, nargs="+", metavar="DIRECTORY")
    mode.add_argument("--approved", type=Path, metavar="PROPOSAL")
    cli.add_argument("--proposal", type=Path, help="New scratch .md preview and companion .json manifest.")
    cli.add_argument("--manifest-sha256", help="Manifest hash recorded with the approved proposal.")
    args = cli.parse_args()
    if bool(args.drafts) != bool(args.proposal):
        cli.error("--proposal is required only with --drafts.")
    if bool(args.approved) != bool(args.manifest_sha256):
        cli.error("--manifest-sha256 is required only with --approved.")
    try:
        result = (review(args.chapter, args.before, args.drafts, args.proposal) if args.drafts
                  else verify_approved(args.chapter, args.before, args.approved, args.manifest_sha256))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (EnrichError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"Enrich review error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
