"""Publication checks for the compact English Enrich chapter."""
from __future__ import annotations

import json
import os
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
from notes import GenerateError
from publication import compile_layout, load_layout
from render_html import Renderer


class EnrichmentPublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.chapter = self.root / "chapter"
        shutil.copytree(FIXTURES / "chapter", self.chapter)
        shutil.copytree(FIXTURES / "enriched", self.chapter, dirs_exist_ok=True)
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

    def modify(self, **changes):
        layout = json.loads(self.layout.read_text(encoding="utf-8"))
        layout.update(changes)
        self.layout.write_text(json.dumps(layout), encoding="utf-8")

    def test_chapter_only_layout_reuses_all_note_links(self):
        model = self.model()
        self.assertEqual([exercise["address"] for exercise in model["exercises"]],
                         ["sequences-demo-exercise-1", "sequences-demo-exercise-2"])
        self.assertEqual([len(exercise["questions"]) for exercise in model["exercises"]], [2, 2])
        self.assertEqual(len(model["questions"]), 4)
        self.assertEqual([len(q["hints"]) for q in model["questions"]], [1, 2, 2, 1])
        self.assertEqual([len(q["explanations"]) for q in model["questions"]], [1, 1, 1, 0])
        self.assertEqual([len(q["corrections"]) for q in model["questions"]], [1, 1, 1, 0])
        self.assertEqual(len(model["course_links"]), 4)
        self.assertNotIn("Replacing", model["questions"][0]["corrections"][0])
        self.assertIn("Replacing", model["questions"][0]["explanations"][0])
        segments = model["exercises"][0]["segments"]
        self.assertIn("Justify each answer.", segments[0]["html"])
        self.assertIn("Consider the sequence", model["exercises"][1]["segments"][0]["html"])
        self.assertEqual(sum("Justify each answer." in str(segment) for segment in segments), 1)
        self.assertNotIn("question::", str(model))

    def test_without_enrichment_preserves_each_ordinary_exercise_unit(self):
        shutil.rmtree(self.chapter)
        shutil.copytree(FIXTURES / "chapter", self.chapter)
        model = self.model()
        self.assertEqual(len(model["exercises"]), 2)
        self.assertEqual(len(model["questions"]), 2)
        self.assertTrue(all(not question["hints"] and not question["explanations"]
                            for question in model["questions"]))
        self.assertIn("Exercise 1", model["questions"][0]["html"])
        self.assertNotIn("Exercise 2", model["questions"][0]["html"])
        self.assertIn("Exercise 2", model["questions"][1]["html"])

    def test_explicit_suppression_and_selected_answer_filtering(self):
        address = "sequences-demo-exercise-1#^q-ex1-1"
        self.modify(questions={address: {"explanations": []}})
        self.assertFalse(self.model()["questions"][0]["explanations"])
        self.modify(questions={address: {"corrections": []}})
        self.assertFalse(self.model()["questions"][0]["explanations"])
        self.assertTrue(self.model()["questions"][0]["hints"])
        self.modify(questions={address: {"corrections": ["sequences-demo-correction-1#Exercise 1"]}})
        self.assertEqual(len(self.model()["questions"][0]["explanations"]), 1)

    def test_invalid_explanation_mappings_fail_explicitly(self):
        path = self.chapter / "aides" / "ex1-q1.md"
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace("#^r-ex1-1", "#^r-ex1-2"), encoding="utf-8")
        with self.assertRaisesRegex(GenerateError, "correction/question mismatch"):
            self.model()
        path.write_text(original, encoding="utf-8")
        self.modify(questions={"sequences-demo-exercise-1#^q-ex1-1": {
            "explanations": ["sequences-demo-aid-ex1-2#^explanation-1"]}})
        with self.assertRaisesRegex(GenerateError, "another question"):
            self.model()
        self.modify(questions={"sequences-demo-exercise-2#^q-ex2-2": {
            "explanations": ["sequences-demo-aid-ex1-1#^explanation-1"]}})
        with self.assertRaisesRegex(GenerateError, "require a selected supplied correction"):
            self.model()

    def test_course_excerpts_are_embedded_even_without_the_reading_view(self):
        self.modify(courses=[])
        model = self.model()
        self.assertFalse(model["reading"])
        self.assertEqual(len(model["courses"]), 4)
        for anchor, target in model["course_links"].items():
            excerpt = next(course for course in model["courses"] if course["id"] == target)
            self.assertIn(f'id="{anchor}"', excerpt["html"])
        generate(self.layout, check=True)

    def test_markdown_course_links_use_the_same_excerpt_mapping(self):
        path = self.chapter / "aides" / "ex1-q1.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "[[sequences-demo-course#Geometric sequences|geometric sequences]]",
            "[geometric sequences](../courses/sequences-demo-course.md#Geometric%20sequences)"),
            encoding="utf-8")
        self.assertEqual(len(self.model()["course_links"]), 4)

    @unittest.skipUnless(os.environ.get("CLEW_TEST_BROWSER") == "1",
                         "Set CLEW_TEST_BROWSER=1 for local browser checks.")
    def test_offline_hint_explanation_and_precise_course_navigation(self):
        from playwright.sync_api import sync_playwright
        generate(self.layout)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()
            failures, requests = [], []
            page.on("pageerror", lambda error: failures.append(str(error)))
            page.route("http://**/*", lambda route: (requests.append(route.request.url), route.abort()))
            page.route("https://**/*", lambda route: (requests.append(route.request.url), route.abort()))
            page.goto((self.root / "sequences.html").as_uri())
            page.wait_for_function("!!window.MathJax?.startup?.document")
            page.get_by_role("button", name="Commencer l'exercice").first.click()
            self.assertEqual(page.locator(".exercise").count(), 2)
            questions = page.locator(".question")
            self.assertEqual(questions.count(), 4)
            self.assertEqual(page.locator('[data-help="explanations"]').count(), 3)
            self.assertEqual(questions.nth(3).locator('[data-action="correction"]').count(), 0)
            questions.nth(1).get_by_role("button", name="Indices", exact=True).click()
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 1)
            page.get_by_role("button", name="Révéler l'indice suivant").click()
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 2)
            page.locator("#reading details").evaluate("node => node.open = true")
            page.locator("#panel-content").get_by_role("link", name="geometric limit result").click()
            self.assertEqual(page.locator("#panel-title").inner_text(), "Geometric limits")
            self.assertIn("For every real constant", page.locator("#panel-content").inner_text())
            self.assertNotIn("Monotone convergence", page.locator("#panel-content").inner_text())
            questions.first.get_by_role("button", name="Afficher la correction", exact=True).click()
            self.assertNotIn("Replacing", questions.first.locator(".correction").inner_text())
            questions.first.get_by_role("button", name="Explications", exact=True).click()
            self.assertIn("Replacing", page.locator("#panel-content").inner_text())
            page.locator("#panel-content").get_by_role("link", name="course definition").click()
            self.assertEqual(page.locator("#panel-title").inner_text(), "Geometric sequences")
            self.assertNotIn("Passing to the limit", page.locator("#panel-content").inner_text())
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator(".exercise").nth(1).evaluate("node => node.open = true")
            questions.nth(3).get_by_role("button", name="Indices", exact=True).click()
            page.locator("#panel-content").get_by_role("link", name="limit relation").click()
            self.assertEqual(page.locator("#panel-title").inner_text(), "Passing to the limit")
            self.assertEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            page.wait_for_function("!document.querySelector('#panel-content .math-inline:not(:has(mjx-container))')")
            self.assertTrue(page.locator("#error").is_hidden())
            self.assertFalse(failures, failures)
            self.assertFalse(requests, requests)
            browser.close()
