import { randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { ReaderError } from "./reader.mjs";

const katexStylesheet = new URL(import.meta.resolve("katex/dist/katex.min.css"));
const ASSETS = new Map([
    ["", ["reader.html", "text/html; charset=utf-8"]],
    ["reader.css", ["reader.css", "text/css; charset=utf-8"]],
    ["reader-client.js", ["reader-client.js", "text/javascript; charset=utf-8"]],
    ["katex/katex.min.css", [katexStylesheet, "text/css; charset=utf-8"]],
]);
const MAX_REQUEST_BYTES = 16384;

function readJson(request, maximum = MAX_REQUEST_BYTES) {
    if (request.headers["content-type"]?.split(";")[0].trim().toLowerCase() !== "application/json") {
        throw new ReaderError("invalid_content_type", "Send an application/json request.", 415);
    }
    return new Promise((resolve, reject) => {
        let size = 0;
        let chunks = [];
        let failed = false;
        request.on("data", (chunk) => {
            if (failed) return;
            size += chunk.length;
            if (size > maximum) {
                chunks = [];
                failed = true;
                reject(new ReaderError("request_too_large", `The request body exceeds the ${maximum}-byte transport bound.`, 413));
            } else chunks.push(chunk);
        });
        request.once("end", () => {
            if (failed) return;
            try {
                resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
            } catch (error) {
                reject(new ReaderError("invalid_json", "The request body is not valid JSON.", 400, { cause: error }));
            }
        });
        request.once("error", reject);
        request.once("aborted", () => reject(new ReaderError("request_aborted", "The request was interrupted.")));
    });
}

function json(response, status, value) {
    response.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
    response.end(JSON.stringify(value));
}

export async function startReaderServer(reader, { stageAttachment, reportError = console.error } = {}) {
    const secret = randomBytes(32).toString("base64url");
    const prefix = `/${secret}/`;
    const clients = new Set();
    const withCapabilities = (state) => ({ ...state, canAskInChat: typeof stageAttachment === "function" });
    const assets = new Map(await Promise.all([...ASSETS].map(async ([route, [file, contentType]]) =>
        [route, { body: await readFile(new URL(file, import.meta.url), "utf8"), contentType }])));
    let origin;

    const server = createServer((request, response) => {
        const nonce = randomBytes(18).toString("base64");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Referrer-Policy", "no-referrer");
        response.setHeader("X-Content-Type-Options", "nosniff");
        response.setHeader("Content-Security-Policy", `default-src 'none'; script-src 'self' 'nonce-${nonce}'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'`);

        async function route() {
            if (request.headers.host !== new URL(origin).host) {
                throw new ReaderError("forbidden_host", "Unexpected loopback host.", 403);
            }
            const url = new URL(request.url, origin);
            if (!url.pathname.startsWith(prefix)) throw new ReaderError("unauthorized", "This reader URL is not authorized.", 403);
            const resource = url.pathname.slice(prefix.length);
            if (request.method === "GET") {
                if (assets.has(resource)) {
                    const asset = assets.get(resource);
                    response.writeHead(200, { "Content-Type": asset.contentType });
                    response.end(asset.body.replaceAll("__CSP_NONCE__", nonce));
                } else if (/^katex\/fonts\/KaTeX_[A-Za-z0-9_-]+\.(woff2?|ttf)$/.test(resource)) {
                    const filename = resource.slice("katex/".length);
                    let font;
                    try {
                        font = await readFile(new URL(filename, katexStylesheet));
                    } catch (error) {
                        if (error.code === "ENOENT") throw new ReaderError("not_found", "KaTeX font not found.", 404);
                        throw error;
                    }
                    const extension = filename.slice(filename.lastIndexOf(".") + 1);
                    response.writeHead(200, { "Content-Type": `font/${extension}` });
                    response.end(font);
                } else if (resource === "api/state") {
                    json(response, 200, withCapabilities(reader.snapshot()));
                } else if (resource === "asset") {
                    const asset = await reader.readAsset(url.searchParams.get("document"),
                        url.searchParams.get("reference"), url.searchParams.get("kind") || "path");
                    response.writeHead(200, { "Content-Type": asset.contentType });
                    response.end(asset.data);
                } else if (resource === "events") {
                    response.writeHead(200, { "Content-Type": "text/event-stream", Connection: "keep-alive" });
                    response.flushHeaders();
                    clients.add(response);
                    response.write(`event: state\ndata: ${JSON.stringify(withCapabilities(reader.snapshot()))}\n\n`);
                    const heartbeat = setInterval(() => response.write(": heartbeat\n\n"), 20000);
                    heartbeat.unref();
                    const cleanup = () => {
                        clients.delete(response);
                        clearInterval(heartbeat);
                    };
                    response.once("close", cleanup);
                    response.once("error", cleanup);
                } else throw new ReaderError("not_found", "Reader resource not found.", 404);
                return;
            }
            if (request.method !== "POST") throw new ReaderError("method_not_allowed", "Use GET or POST.", 405);
            if (request.headers.origin !== origin) throw new ReaderError("forbidden_origin", "Reader actions require the same loopback origin.", 403);
            const commands = {
                "api/navigate": (input) => reader.navigate(input),
                "api/follow": (input) => reader.follow(input),
                "api/refresh": (input) => reader.refresh(input),
                "api/attach": (input) => reader.attachSelection(input, stageAttachment),
            };
            if (!Object.hasOwn(commands, resource)) throw new ReaderError("not_found", "Reader action not found.", 404);
            // Any selection fits within the rendered page; allow worst-case JSON escaping plus metadata.
            const maximum = resource === "api/attach"
                ? Buffer.byteLength(reader.note.html, "utf8") * 6 + MAX_REQUEST_BYTES
                : MAX_REQUEST_BYTES;
            const input = await readJson(request, maximum);
            if (!Number.isSafeInteger(input?.expectedRevision) || input.expectedRevision < 1) {
                throw new ReaderError("invalid_input", "expectedRevision is required for reader actions.");
            }
            const result = await commands[resource](input);
            json(response, 200, resource === "api/attach" ? result : withCapabilities(result));
        }

        route().catch((error) => {
            const known = error instanceof ReaderError;
            if (!known) reportError(error);
            if (!response.headersSent && !response.destroyed) {
                json(response, known ? error.status : 500, {
                    error: { code: known ? error.code : "internal_error",
                        message: known ? error.message : "The reader could not complete the request. Check the extension log." },
                });
            } else if (!response.destroyed) response.end();
        });
    });
    server.requestTimeout = 10000;
    await new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", resolve);
    });
    const address = server.address();
    if (!address || typeof address === "string") throw new Error("The loopback server did not receive a TCP port.");
    origin = `http://127.0.0.1:${address.port}`;
    server.on("error", reportError);
    const update = (state) => {
        for (const client of clients) {
            if (client.destroyed || client.writableLength > 2 * 1024 * 1024) client.destroy();
            else client.write(`event: state\ndata: ${JSON.stringify(withCapabilities(state))}\n\n`);
        }
    };
    reader.on("state", update);
    let closing;
    return {
        url: `${origin}${prefix}`,
        close: () => closing ??= (async () => {
            reader.off("state", update);
            for (const client of clients) client.end();
            await new Promise((resolve, reject) => {
                server.close((error) => error ? reject(error) : resolve());
                server.closeAllConnections();
            });
        })(),
    };
}
