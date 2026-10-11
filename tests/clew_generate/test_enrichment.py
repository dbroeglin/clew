"""Publication of the current Import-shaped Enrich integration fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "clew-generate"
FIXTURES = ROOT / "tests" / "clew_enrich" / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))

from generate_html import generate
from publication import compile_layout, load_layout
from render_html import Renderer


class EnrichmentPublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.chapter = self.root / "chapter"
        shutil.copytree(FIXTURES / "chapter", self.chapter)
        self.layout = self.root / "layout.json"
        self.layout.write_text(json.dumps({
            "schema_version": 1, "title": "Sequence worksheet",
            "notes": [str(self.chapter)], "output": "sequences.html",
        }), encoding="utf-8")

    def model(self):
        layout, library = load_layout(self.layout)
        renderer = Renderer(library, Path(layout["output"]))
        model = compile_layout(layout, library, renderer)
        renderer.validate_links()
        return model

    def test_import_only_keeps_existing_question_units(self):
        model = self.model()
        self.assertEqual([e["address"] for e in model["exercises"]], ["sheet#^ex-1"])
        self.assertEqual(len(model["questions"]), 3)
        self.assertEqual([len(q["corrections"]) for q in model["questions"]], [1, 1, 0])
        self.assertEqual([len(q["hints"]) for q in model["questions"]], [0, 1, 0])
        self.assertTrue(all(not q["explanations"] for q in model["questions"]))

    def test_enriched_chapter_reuses_current_aid_links(self):
        shutil.copytree(FIXTURES / "enriched", self.chapter, dirs_exist_ok=True)
        model = self.model()
        self.assertEqual([len(q["hints"]) for q in model["questions"]], [1, 1, 0])
        self.assertEqual([len(q["explanations"]) for q in model["questions"]], [1, 0, 0])
        self.assertEqual(len(model["course_links"]), 2)
        self.assertNotIn("ratio has absolute", model["questions"][0]["corrections"][0])
        self.assertIn("ratio has absolute", model["questions"][0]["explanations"][0])
        generate(self.layout, check=True)

    def test_no_preparation_record_or_baseline_is_read(self):
        shutil.copytree(FIXTURES / "enriched", self.chapter, dirs_exist_ok=True)
        (self.chapter / ".clew" / "preparation.json").write_text("not consulted", encoding="utf-8")
        (self.chapter / ".clew" / "baselines").mkdir()
        (self.chapter / ".clew" / "baselines" / "invalid.md").write_text("private", encoding="utf-8")
        generate(self.layout, check=True)
