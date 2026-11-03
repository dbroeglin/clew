"""Browser checks for the Clew canvas front-end, served by the real extension code with a fake session.

Opt-in: set CLEW_TEST_BROWSER=1. CLEW_TEST_HEADED=1 shows the browser and
CLEW_TEST_SCREENSHOTS=<dir> saves a screenshot after every scenario and on failure.
Requires Node.js, Microsoft Edge and the root dev dependencies (Playwright).
"""
import json
import os
import subprocess
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).with_name("browser_harness.mjs")
Q1, Q2, Q3 = "sheet#^q-1", "sheet#^q-2", "sheet#^q-3"
HINT_TEXT = ("Compare", "Apply")


def question(address):
    return f'.sheet .question[data-address="{address}"]'


@unittest.skipUnless(os.environ.get("CLEW_TEST_BROWSER") == "1",
                     "Set CLEW_TEST_BROWSER=1 for local browser checks.")
class CanvasBrowserTest(unittest.TestCase):
    def setUp(self):
        self.harness = subprocess.Popen(["node", str(HARNESS)], cwd=REPO, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self.addCleanup(self.quit)
        self.info = json.loads(self.harness.stdout.readline())
        self.vault = Path(self.info["vault"])
        self.shots = Path(os.environ["CLEW_TEST_SCREENSHOTS"]) if os.environ.get("CLEW_TEST_SCREENSHOTS") else None
        if self.shots:
            self.shots.mkdir(parents=True, exist_ok=True)
        self.step = 0

    def quit(self):
        try:
            if self.harness.poll() is None:
                self.harness.stdin.write('{"cmd":"quit"}\n')
                self.harness.stdin.close()
                try:
                    self.harness.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.harness.kill()
                    self.harness.wait()
        finally:
            self.harness.stdout.close()

    def cmd(self, name, **args):
        self.harness.stdin.write(json.dumps({"cmd": name, **args}) + "\n")
        self.harness.stdin.flush()
        reply = json.loads(self.harness.stdout.readline())
        if not reply["ok"]:
            raise AssertionError(f"{name}: {reply['error']}")
        return reply["result"]

    def shot(self, page, name):
        self.step += 1
        if self.shots:
            page.screenshot(path=str(self.shots / f"{self.step:02d}-{name}.png"), full_page=True)

    def wait_state(self, predicate, timeout=15, **query):
        deadline = time.monotonic() + timeout
        while True:
            state = self.cmd("state", instance="c1", **query)
            if predicate(state):
                return state
            if time.monotonic() > deadline:
                self.fail(f"State condition not met: {json.dumps(state, ensure_ascii=False)[:2000]}")
            time.sleep(0.2)

    @staticmethod
    def progress(state, address):
        for exercise in state.get("exercises", []):
            for item in exercise.get("progress", []):
                if item["address"] == address:
                    return item
        return {}

    def toast(self, page, text):
        page.wait_for_function("text => { const box = document.getElementById('toast');"
                               " return !box.hidden && box.textContent.includes(text); }", arg=text)

    def test_canvas_reader_in_browser(self):
        from playwright.sync_api import sync_playwright
        url = self.cmd("open", instance="c1")["url"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge",
                                                 headless=os.environ.get("CLEW_TEST_HEADED") != "1")
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            failures, remote = [], []
            page.on("pageerror", lambda error: failures.append(str(error)))
            page.route("https://**/*", lambda route: (remote.append(route.request.url), route.abort()))
            try:
                self.journey(page, url)
            except BaseException:
                self.shot(page, "failure")
                raise
            self.assertEqual(failures, [])
            self.assertEqual(remote, [])

    def journey(self, page, url):
        # Rendering, theme and MathJax.
        page.goto(url)
        page.wait_for_function("() => document.getElementById('title').textContent === 'Suites · révision'")
        self.assertEqual(page.locator(".sheet .exercise").count(), 2)
        self.assertEqual(page.locator(".sheet .question").count(), 0)
        self.assertEqual(page.locator("#reading details").count(), 1)
        self.assertEqual(page.locator("#reading .course-navigation select option").count(), 0)
        self.assertEqual(page.locator("#reading .course-body h1").count(), 0)
        self.assertTrue(page.locator("#status").is_hidden())
        self.assertIn(page.evaluate("() => document.documentElement.dataset.theme"), ("light", "dark"))
        page.evaluate("() => document.documentElement.setAttribute('data-color-mode', 'dark')")
        page.wait_for_function("() => document.documentElement.dataset.theme === 'dark'")
        self.shot(page, "rendered-dark-theme")
        page.evaluate("() => document.documentElement.setAttribute('data-color-mode', 'light')")
        page.wait_for_function("() => document.documentElement.dataset.theme === 'light'")

        page.get_by_role("button", name="Start exercise").first.click()
        page.wait_for_selector(".sheet .exercise[open] mjx-container svg")
        self.assertGreater(page.locator(".sheet .question").count(), 0)
        self.wait_state(lambda s: s["exercises"][0].get("started"))
        self.shot(page, "exercise-started-math")

        # Hints, course link inside a hint, Back and Close.
        q1 = page.locator(question(Q1))
        q1.get_by_role("button", name="Hints", exact=True).click()
        self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 1)
        page.get_by_role("button", name="Reveal next hint").click()
        self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 2)
        self.assertTrue(page.get_by_role("button", name="Reveal next hint").is_hidden())
        self.wait_state(lambda s: self.progress(s, Q1).get("hints") == "2/2")
        self.shot(page, "hints-revealed")
        page.locator("#panel-content").get_by_role("link", name="the geometric limit result").click()
        page.wait_for_function("() => document.getElementById('panel-title').textContent === 'Geometric limit result'")
        self.wait_state(lambda s: any(c["address"] == "course#^theorem" for c in s["courses_opened"]))
        self.shot(page, "course-from-hint")
        page.get_by_role("button", name="Back", exact=True).click()
        page.wait_for_function("() => document.getElementById('panel-title').textContent.startsWith('Hints')")
        self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 2)
        page.get_by_role("button", name="Close", exact=True).click()
        self.assertEqual(page.locator("#panel-title").inner_text(), "Contextual help")

        # Supplied correction.
        q1.get_by_role("button", name="Show correction").click()
        page.wait_for_selector(f"{question(Q1)} .correction:not([hidden]) mjx-container, "
                               f"{question(Q1)} .correction:not([hidden])")
        self.wait_state(lambda s: self.progress(s, Q1).get("correction_viewed"))
        self.shot(page, "correction-shown")

        # Published PDF links open through the extension; missing files and opener failures are reported.
        q1.locator('a[href*="sheet.pdf#page=1"]').first.click()
        self.toast(page, "Opened in your browser.")
        target = self.cmd("opened")[-1]
        self.assertIn("/vault/Maths/Suites%20r%C3%A9vision/Exercise-sheet/sheet.pdf?t=", target)
        self.assertTrue(target.endswith("#page=1"))
        served = page.request.get(target.split("#")[0])
        self.assertEqual(served.status, 200)
        self.assertEqual(served.headers["content-type"], "application/pdf")
        self.shot(page, "pdf-opened")
        page.locator("#reading details > summary").click()
        navigation = page.locator("#reading .course-navigation")
        page.wait_for_function("() => document.querySelector('#reading .course-navigation select')?.options.length === 2")
        self.assertEqual(page.locator("#reading .course-body h1").all_text_contents(), ["Geometric limits"])
        table = page.locator("#reading .course-body table")
        self.assertEqual(table.count(), 1)
        self.assertEqual(table.locator("tr").count(), 2)
        self.assertEqual(table.locator("td").all_text_contents(),
                         ["independent", "must be independent"])
        navigation.get_by_role("button", name="Next section").click()
        self.assertEqual(page.locator("#reading .course-body h1").all_text_contents(), ["Subsequences"])
        self.assertEqual(page.locator("#reading .course-body h1").count(), 1)
        self.assertEqual(navigation.locator('[data-slot="section-position"]').inner_text(), "Section 2 of 2")
        self.wait_state(lambda s: any(section["title"] == "Subsequences" for section in s["course_sections_opened"]))
        self.shot(page, "course-section-navigation")
        navigation.get_by_role("button", name="Previous section").click()
        self.assertEqual(page.locator("#reading .course-body h1").all_text_contents(), ["Geometric limits"])
        page.locator('#reading a[href*="course.pdf"]').first.click()
        self.toast(page, "PDF not found: course.pdf")
        self.assertEqual(len(self.cmd("opened")), 1)
        self.shot(page, "failure-missing-pdf")
        self.cmd("opener", fails=True)
        q1.locator('a[href*="sheet.pdf#page=1"]').first.click()
        self.toast(page, "Could not open link")
        self.shot(page, "failure-opener")
        self.cmd("opener", fails=False)

        digest = self.cmd("digest")["additionalContext"]
        self.assertIn("revealed hint 2/2", digest)
        self.assertIn("opened the PDF", digest)
        self.assertIn('opened section 2/2 "Subsequences"', digest)
        self.assertIsNone(self.cmd("digest"))

        # Ask the tutor: fixed visible prompt, hidden context without hint contents.
        q1.get_by_role("button", name="Ask the tutor").click()
        self.toast(page, "Request sent to the tutor")
        sent = self.cmd("sent")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["displayPrompt"], "I need help with this question")
        self.assertIn(f"[{Q1}]", sent[0]["prompt"])
        self.assertIn("hints revealed 2/2", sent[0]["prompt"])
        for text in HINT_TEXT:
            self.assertNotIn(text, sent[0]["prompt"])
        self.assertTrue(q1.get_by_role("button", name="Ask the tutor").is_disabled())
        self.shot(page, "tutor-asked")

        # Tutor show: scrolls and highlights without recording student actions.
        shown = self.cmd("show", instance="c1", target=Q3)
        self.assertEqual(shown, {"shown": "question", "address": Q3, "delivered": True})
        page.wait_for_selector(f"{question(Q3)}.clew-shown")
        self.assertEqual(page.locator(question(Q3)).count(), 1)
        self.toast(page, "Your tutor is showing you: Question 3")
        self.shot(page, "tutor-show-question")
        self.cmd("show", instance="c1", target="course#Geometric limits")
        page.wait_for_function("() => document.getElementById('panel-title').textContent === 'Geometric limits'")
        self.shot(page, "tutor-show-course")
        state = self.cmd("state", instance="c1")
        self.assertFalse(state["exercises"][1].get("started", False))
        self.assertFalse(any(c["address"] == "course#Geometric limits" for c in state["courses_opened"]))
        self.assertIsNone(self.cmd("digest"))

        # Live reload after a note edit keeps the open exercise and correction.
        page.locator("#reading .course-navigation").get_by_role("button", name="Next section").click()
        self.assertEqual(page.locator("#reading .course-body h1").all_text_contents(), ["Subsequences"])
        sheet = Path(self.info["chapter"]) / "Exercise-sheet" / "sheet.md"
        sheet.write_text(sheet.read_text(encoding="utf-8").replace("2. Find a bound.", "2. Find an upper bound."),
                         encoding="utf-8")
        page.wait_for_function(f"() => document.querySelector('{question(Q2)}')?.textContent.includes('upper bound')",
                               timeout=30000)
        self.assertTrue(page.locator(f"{question(Q1)} .correction").is_visible())
        self.assertEqual(page.evaluate("() => document.querySelector('.sheet .exercise').open"), True)
        self.assertEqual(page.locator("#reading .course-body h1").all_text_contents(), ["Subsequences"])
        self.shot(page, "live-reload")

        # A course without top-level headings remains one valid, recordable view.
        course = Path(self.info["chapter"]) / "Course-course" / "course.md"
        course.write_text(course.read_text(encoding="utf-8").replace(
            "# Geometric limits", "## Geometric limits").replace("# Subsequences", "## Subsequences"),
            encoding="utf-8")
        page.wait_for_function("() => Array.from(document.querySelectorAll('#reading .course-body h2'))"
                               ".some(heading => heading.textContent.includes('Subsequences')) "
                               "&& document.querySelector('#reading .course-navigation').hidden", timeout=30000)
        details = page.locator("#reading details")
        if details.evaluate("(element) => element.open"):
            details.locator("summary").click()
            page.wait_for_function("() => !document.querySelector('#reading details').open")
        details.locator("summary").click()
        page.wait_for_function("() => document.querySelector('#reading details').open")
        self.wait_state(lambda s: any(section["title"] == "Course" and section["total"] == 1
                                      for section in s["course_sections_opened"]))
        self.shot(page, "course-single-view")

        # A broken layout keeps the last content with a visible status, then recovers.
        layout = Path(self.info["layout"])
        original = layout.read_text(encoding="utf-8")
        layout.write_text(original.replace("Suites r\\u00e9vision", "Missing").replace("Suites révision", "Missing"),
                          encoding="utf-8")
        page.wait_for_function("() => { const status = document.getElementById('status'); "
                               "return status.dataset.status === 'stale' && !status.hidden "
                               "&& status.textContent.includes('Content is out of date'); }", timeout=30000)
        self.assertIn("Content is out of date", page.locator("#status").inner_text())
        self.assertEqual(page.locator(".sheet .question").count(), 3)
        self.shot(page, "failure-compile-error")
        layout.write_text(original, encoding="utf-8")
        page.wait_for_selector("#status[hidden]", state="attached", timeout=30000)

        # A paused session shows the banner, buffers events and delivers them after the restart.
        self.cmd("pause")
        page.wait_for_selector("#server-error:not([hidden])", timeout=15000)
        page.locator(question(Q2)).get_by_role("button", name="Show correction").click()
        self.shot(page, "failure-session-paused")
        self.cmd("resume")
        page.wait_for_selector("#server-error", state="hidden", timeout=30000)
        self.wait_state(lambda s: self.progress(s, Q2).get("correction_viewed"), timeout=45)
        self.shot(page, "session-resumed")

        # Activity record in the vault.
        activity = self.vault / self.cmd("state", instance="c1")["activity"]
        self.cmd("close", instance="c1")
        events = [json.loads(line) for line in (activity / "activity.jsonl").read_text(encoding="utf-8").splitlines()]
        types = {event.get("type") for event in events}
        for expected in ("canvas_opened", "exercise_started", "hint_revealed", "course_opened", "course_section_opened",
                         "correction_shown", "pdf_opened", "tutor_requested", "tutor_show", "content_changed", "canvas_closed"):
            self.assertIn(expected, types)
        summary = (activity / "summary.md").read_text(encoding="utf-8")
        self.assertIn("Question 1", summary)
        self.assertIn("Section 2/2 · Subsequences", summary)
        self.assertIn("Suites · révision", summary)


if __name__ == "__main__":
    unittest.main()
