import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { CourseReader, resolveCourse } from "../reader.mjs";

export async function fixture(t, { stageAttachment } = {}) {
    const root = await mkdtemp(path.join(tmpdir(), "clew-reader-test-"));
    t.after(() => rm(root, { recursive: true, force: true }));
    const vaultPath = path.join(root, "vault");
    const courseRoot = path.join(vaultPath, "courses", "demo");
    const workspacePath = path.join(root, "session");
    await mkdir(courseRoot, { recursive: true });
    await mkdir(workspacePath);
    await writeFile(path.join(courseRoot, "hub.md"), "---\ntitle: Course home\nprevious: null\nnext: lessons/one.md\n---\n# Course home\n\nStart here.\n");
    await mkdir(path.join(courseRoot, "lessons"));
    await writeFile(path.join(courseRoot, "lessons", "one.md"),
        "---\nprevious: '[[courses/demo/hub|Home]]'\nnext: '[[two]]'\n---\n# First lesson\n\nSome **grounded** text.\n");
    await writeFile(path.join(courseRoot, "two.md"), "---\nprevious: lessons/one.md\nnext: null\n---\n# Second lesson\n\n## A heading\n\nThe end.\n");
    const attachments = [];
    const course = await resolveCourse({ vaultPath, coursePath: "courses/demo" });
    const options = { ...course, workspacePath };
    const stage = stageAttachment || (async (attachment) => { attachments.push(attachment); });
    const reader = new CourseReader(options);
    await reader.initialize();
    return { root, vaultPath, courseRoot, workspacePath, course, reader, attachments, stageAttachment: stage, options };
}
