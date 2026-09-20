// A single actionable error type for the capture layer, mirroring the course
// reader's ReaderError so the SDK adapter can map it to a CanvasError code.
export class CaptureError extends Error {
    constructor(code, message) {
        super(message);
        this.name = "CaptureError";
        this.code = code;
    }
}
