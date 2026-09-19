import { CanvasError, createCanvas, joinSession } from "@github/copilot-sdk/extension";
import { CourseReader, ReaderError, objectInput, resolveCourse } from "./reader.mjs";
import { startReaderServer } from "./server.mjs";

const panels = new Map();
const courses = new Map();
const string = { type: "string", minLength: 1, maxLength: 4096 };
const expectedRevision = { type: "integer", minimum: 1 };
const schema = (properties, required = []) => ({
    type: "object", properties, required, additionalProperties: false,
});
let session;

async function invoke(operation) {
    try {
        return await operation();
    } catch (error) {
        if (error instanceof ReaderError) throw new CanvasError(error.code, error.message);
        console.error(error);
        throw new CanvasError("reader_error", "The course reader failed. Inspect the extension log for details.");
    }
}

async function activeReader(instanceId) {
    const panel = await panels.get(instanceId);
    if (!panel) throw new ReaderError("reader_not_open", "Open the course reader before invoking an action.", 404);
    return panel.reader;
}

function action(name, description, inputSchema, command) {
    return {
        name, description, inputSchema,
        handler: (ctx) => invoke(async () => {
            const reader = await activeReader(ctx.instanceId);
            await command(reader, ctx.input ?? {});
            return reader.snapshot({ forAgent: true });
        }),
    };
}

async function createPanel(input, instanceId) {
    if (!session) throw new ReaderError("session_not_ready", "The extension is still joining the session; reopen the reader.", 503);
    const course = await resolveCourse(input);
    let pending = courses.get(course.courseRoot);
    if (!pending) {
        pending = (async () => {
            const reader = new CourseReader({
                ...course, workspacePath: session.workspacePath,
            });
            await reader.initialize(course.entry);
            return reader;
        })();
        courses.set(course.courseRoot, pending);
        pending.catch(() => courses.delete(course.courseRoot));
    }
    const reader = await pending;
    const stageAttachment = typeof session.rpc.extensions?.sendAttachmentsToMessage === "function"
        ? (attachment) => session.rpc.extensions.sendAttachmentsToMessage({
            instanceId, attachments: [attachment],
        })
        : undefined;
    return { reader, server: await startReaderServer(reader, { stageAttachment }) };
}

const canvas = createCanvas({
    id: "clew-course-reader",
    displayName: "Clew Course Reader",
    description: "Read a vault course with math, navigate authored links, and stage selected passages in the chat composer.",
    inputSchema: schema({
        vaultPath: { ...string, description: "Absolute path of the current vault; supplied explicitly, never auto-discovered." },
        coursePath: { ...string, description: "Course directory relative to that vault, not the entire vault or learner model." },
        entry: { ...string, description: "Initial course-relative note (default hub.md); an existing reading position takes precedence." },
    }, ["vaultPath", "coursePath"]),
    actions: [
        action("get_state", "Get the current page, navigation and grounded excerpt; never reads learner records.",
            schema({}), (reader, input) => objectInput(input, [])),
        action("open_page", "Display a course-relative Markdown note and update every view of this course.",
            schema({ path: string, expectedRevision }, ["path"]), (reader, input) => reader.openPage(input)),
        action("navigate", "Follow the current page's previous or next frontmatter link.",
            schema({ direction: { enum: ["previous", "next"] }, expectedRevision }, ["direction"]),
            (reader, input) => reader.navigate(input)),
        action("refresh", "Reload the current note from disk and push it to the reader without sending a chat message.",
            schema({ expectedRevision }), (reader, input) => reader.refresh(input)),
    ],
    open: (ctx) => invoke(async () => {
        let pending = panels.get(ctx.instanceId);
        if (!pending) {
            pending = createPanel(ctx.input, ctx.instanceId);
            panels.set(ctx.instanceId, pending);
            pending.catch(() => {
                if (panels.get(ctx.instanceId) === pending) panels.delete(ctx.instanceId);
            });
        }
        const panel = await pending;
        return { url: panel.server.url, title: "Clew Course Reader", status: panel.reader.note.title };
    }),
    onClose: (ctx) => invoke(async () => {
        const pending = panels.get(ctx.instanceId);
        if (pending) {
            panels.delete(ctx.instanceId);
            const panel = await pending;
            await panel.server.close();
        }
    }),
});

session = await joinSession({ canvases: [canvas] });

let closing = false;
async function shutdown() {
    if (closing) return;
    closing = true;
    const results = await Promise.allSettled([...panels.values()].map(async (pending) => (await pending).server.close()));
    for (const result of results) if (result.status === "rejected") console.error(result.reason);
    process.exit(results.some((result) => result.status === "rejected") ? 1 : 0);
}
process.once("SIGTERM", shutdown);
process.once("SIGINT", shutdown);
process.once("disconnect", shutdown);
