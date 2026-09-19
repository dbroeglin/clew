import assert from "node:assert/strict";
import { realpath, writeFile } from "node:fs/promises";
import path from "node:path";
import { after, before, test } from "node:test";
import { chromium } from "playwright";
import { startReaderServer } from "../server.mjs";
import { fixture } from "../test/fixtures.mjs";

let browser;
before(async () => {
    browser = await chromium.launch({
        channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === "win32" ? "msedge" : undefined),
        headless: true,
    });
});
after(async () => browser?.close());

async function browserFixture(t, source, { canStage = true, stageAttachment } = {}) {
    const data = await fixture(t, { stageAttachment });
    if (source) {
        await writeFile(path.join(data.courseRoot, "hub.md"), source);
        await data.reader.refresh();
    }
    const server = await startReaderServer(data.reader, {
        stageAttachment: canStage ? data.stageAttachment : undefined,
    });
    t.after(() => server.close());
    const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
    t.after(() => page.close());
    return { ...data, server, page };
}

async function selectText(page, selector) {
    return page.locator(selector).first().evaluate((element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        return selection.toString();
    });
}

test("minimal reader preserves math, navigation, contents preference and session updates", { timeout: 60000 }, async (t) => {
    const { reader, server, page, attachments } = await browserFixture(t, [
        "---", "title: Course home", "previous: null", "next: lessons/one.md", "---",
        "# Course home", "", "Inline $a^2+b^2=c^2$ and a display formula:", "",
        "## Formula", "",
        "$$", "\\int_0^1 x^2\\,dx = \\frac{1}{3}", "$$",
    ].join("\n"));
    const errors = [];
    const resources = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => resources.push({ url: response.url(), status: response.status() }));
    await page.goto(server.url);
    await page.locator("#course-home").waitFor();
    assert.equal(await page.locator(".katex").count(), 2);
    assert.equal(await page.locator("math").count(), 2);
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.evaluate(() => document.fonts.check('16px "KaTeX_Main"')), true);
    assert.ok(resources.some((resource) => resource.url.includes("KaTeX_Main-Regular.woff2") && resource.status === 200),
        `The actual KaTeX font was not loaded. Resources: ${JSON.stringify(resources)}`);
    assert.ok(resources.every((resource) => new URL(resource.url).origin === new URL(server.url).origin));
    assert.equal(await page.getByRole("button", { name: /^Previous\b/ }).isDisabled(), true);
    const controls = await page.locator("button:visible").evaluateAll((elements) =>
        elements.map((element) => element.getAttribute("aria-label") || element.textContent.trim()));
    assert.deepEqual(controls.sort(), ["Next", "Previous"]);
    assert.equal(await page.getByRole("button", { name: /Explain this page|Send excerpt|Refresh|Ask in chat/ }).count(), 0);
    assert.equal(await page.locator("dialog").count(), 0);
    const contents = page.locator("details");
    assert.equal(await contents.evaluate((element) => element.open), false);
    if (process.env.CLEW_READER_SCREENSHOT) await page.screenshot({ path: process.env.CLEW_READER_SCREENSHOT, fullPage: true });

    await contents.locator("summary").click();
    assert.equal(await contents.evaluate((element) => element.open), true);
    await contents.locator('a[href="#formula"]').click();
    assert.equal(await page.evaluate(() => document.activeElement?.id), "formula");
    await page.setViewportSize({ width: 360, height: 800 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true);
    await page.getByRole("button", { name: /^Next\b/ }).click();
    await page.locator("#first-lesson").waitFor();
    assert.equal(reader.snapshot().path, "lessons/one.md");
    await page.getByRole("button", { name: /^Previous\b/ }).click();
    await page.locator("#course-home").waitFor();
    assert.equal(await contents.evaluate((element) => element.open), true);
    await reader.openPage({ path: "two.md" });
    await page.locator("#second-lesson").waitFor();
    assert.equal(await page.getByRole("button", { name: /^Next\b/ }).isDisabled(), true);
    assert.equal(attachments.length, 0);
    assert.deepEqual(errors, []);

    await server.close();
    await page.getByText(/reconnecting|connection lost|offline/i).first().waitFor();
    assert.equal(await page.locator("#second-lesson").isVisible(), true);
});

test("selected passages become composer attachments only after an explicit action", { timeout: 60000 }, async (t) => {
    const { reader, server, page, attachments } = await browserFixture(t);
    await page.goto(server.url);
    await page.locator("#course-home").waitFor();
    const text = await selectText(page, "article p");
    const ask = page.getByRole("button", { name: "Ask in chat", exact: true });
    await ask.waitFor();
    assert.equal(attachments.length, 0);
    const intents = [];
    page.on("request", (request) => {
        if (request.url().endsWith("/api/attach")) intents.push(request.postDataJSON());
    });
    await page.route("**/api/attach", (route) => route.fulfill({
        status: 503, contentType: "application/json",
        body: JSON.stringify({ error: { code: "composer_unavailable", message: "Synthetic composer is unavailable." } }),
    }));
    await ask.click();
    await page.getByText("Synthetic composer is unavailable.").waitFor();
    assert.equal(attachments.length, 0);
    await page.unroute("**/api/attach");
    const [staging] = await Promise.all([
        page.waitForResponse((response) => response.url().endsWith("/api/attach")),
        ask.click(),
    ]);
    assert.equal(staging.status(), 200);
    assert.equal((await staging.json()).staged, true);
    assert.equal(attachments.length, 1);
    assert.equal(attachments[0].type, "extension_context");
    assert.equal(attachments[0].payload.text, text);
    assert.equal(intents[0].requestId, intents[1].requestId);
    await ask.waitFor({ state: "hidden" });
    await selectText(page, "article p");
    await ask.waitFor();
    await reader.navigate({ direction: "next" });
    await page.locator("#first-lesson").waitFor();
    await ask.waitFor({ state: "hidden" });
    assert.equal(attachments.length, 1);
});

test("mouse selection inside an iframe exposes the contextual action", { timeout: 60000 }, async (t) => {
    const { page, server, attachments } = await browserFixture(t);
    await page.setContent(`<iframe title="Reader" src="${server.url}" sandbox="allow-scripts allow-same-origin" style="width:700px;height:650px;border:0"></iframe>`);
    const frame = page.frameLocator("iframe");
    const paragraph = frame.locator("article p").first();
    await paragraph.waitFor();
    const rectangle = await paragraph.evaluate((element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        const bounds = range.getBoundingClientRect();
        return { left: bounds.left, right: bounds.right, y: bounds.top + bounds.height / 2 };
    });
    const iframe = await page.locator("iframe").boundingBox();
    await page.mouse.move(iframe.x + rectangle.left + 0.5, iframe.y + rectangle.y);
    await page.mouse.down();
    await page.mouse.move(iframe.x + rectangle.right - 0.5, iframe.y + rectangle.y, { steps: 12 });
    await page.mouse.up();
    const text = await paragraph.evaluate(() => window.getSelection().toString());
    assert.equal(text, "Start here.");
    const ask = frame.getByRole("button", { name: "Ask in chat", exact: true });
    await ask.waitFor();
    assert.equal(attachments.length, 0);
    const completion = page.waitForResponse((result) => result.url().endsWith("/api/attach"), { timeout: 5000 })
        .then((response) => ({ response }), (error) => ({ error }));
    await ask.click();
    const result = await completion;
    if (result.error) {
        const diagnostics = await frame.locator("body").evaluate(() => ({
            errors: [...document.querySelectorAll('[role="alert"]')].map((element) => element.textContent),
            selection: window.getSelection().toString(),
            secureContext: window.isSecureContext,
            randomUUID: typeof crypto.randomUUID,
        }));
        assert.fail(`No attachment request: ${JSON.stringify(diagnostics)}`);
    }
    const response = result.response;
    assert.equal(response.status(), 200);
    assert.equal(attachments[0].payload.text, text);
});

test("keyboard activation stages the complete long selection, not the tool excerpt", { timeout: 60000 }, async (t) => {
    const passage = "A full selected passage. ".repeat(800);
    const { page, server, attachments } = await browserFixture(t, "# Course home\n\n" + passage);
    await page.goto(server.url);
    await page.locator("#course-home").waitFor();
    const selected = await selectText(page, "article p");
    assert.ok(selected.length > 12000);
    const ask = page.getByRole("button", { name: "Ask in chat", exact: true });
    await ask.waitFor();
    await ask.focus();
    const [response] = await Promise.all([
        page.waitForResponse((result) => result.url().endsWith("/api/attach")),
        page.keyboard.press("Enter"),
    ]);
    assert.equal(response.status(), 200);
    assert.equal(attachments[0].payload.text, selected);
});

test("rendered selections carry the source file and starting section without guessed references", { timeout: 60000 }, async (t) => {
    const { page, server, courseRoot, attachments } = await browserFixture(t, [
        "A preface before any heading.", "", "# Course home", "",
        "## First section", "", "A passage with **emphasis**.", "",
        "## Last section", "", "The final passage.",
    ].join("\n"));
    await page.goto(server.url);
    await page.locator("#first-section").waitFor();
    const ask = page.getByRole("button", { name: "Ask in chat", exact: true });
    for (const [selector, heading] of [
        ["article p:nth-of-type(2)", { id: "first-section", text: "First section" }],
        ["article p:nth-of-type(3)", { id: "last-section", text: "Last section" }],
        ["article p:nth-of-type(1)", null],
    ]) {
        const text = await selectText(page, selector);
        await ask.waitFor();
        const [response] = await Promise.all([
            page.waitForResponse((result) => result.url().endsWith("/api/attach")),
            ask.click(),
        ]);
        assert.equal(response.status(), 200);
        const attachment = attachments.at(-1);
        assert.equal(attachment.type, "extension_context");
        assert.equal(attachment.payload.filePath, await realpath(path.join(courseRoot, "hub.md")));
        assert.deepEqual(attachment.payload.heading, heading);
        assert.equal(attachment.payload.text, text);
        await ask.waitFor({ state: "hidden" });
    }
    assert.equal(attachments.length, 3);
});

test("unsupported composers and selections outside the course content offer no action", { timeout: 60000 }, async (t) => {
    const { page, server, attachments } = await browserFixture(t, undefined, { canStage: false });
    await page.goto(server.url);
    await page.locator("#course-home").waitFor();
    await selectText(page, "article p");
    assert.equal(await page.getByRole("button", { name: "Ask in chat", exact: true }).isVisible(), false);
    assert.equal(attachments.length, 0);

    const supported = await browserFixture(t);
    await supported.page.goto(supported.server.url);
    await supported.page.locator("#course-home").waitFor();
    assert.ok((await selectText(supported.page, "button")).trim().length > 0);
    await supported.page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)));
    assert.equal(await supported.page.getByRole("button", { name: "Ask in chat", exact: true }).isVisible(), false);
    assert.equal(supported.attachments.length, 0);
});

test("broken navigation and untrusted HTML stay visible and do not execute", { timeout: 60000 }, async (t) => {
    const { page, server, reader } = await browserFixture(t,
        "---\nnext: missing.md\n---\n# Course home\n\n<script>window.readerUnsafe = true;</script>\n");
    await page.goto(server.url);
    await page.locator("#course-home").waitFor();
    assert.equal(await page.getByRole("button", { name: /^Next\b/ }).isDisabled(), true);
    await page.getByText(/was not found/).waitFor();
    assert.equal(await page.evaluate(() => window.readerUnsafe), undefined);
    assert.equal(reader.snapshot().path, "hub.md");
});
