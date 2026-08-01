/**
 * Client side of the code runner.
 *
 * The whole design is one sentence: the app never executes the code it is
 * asked to run. It hands the code to `/api/code/runner`, an iframe framed with
 * `sandbox="allow-scripts"` and pointedly *not* `allow-same-origin`, which
 * gives that document an opaque origin — no cookies, no storage, no reach into
 * this DOM, and no way to call the K-OS API as the signed-in person. This file
 * is the postMessage plumbing on this side of that wall.
 *
 * The wall matters because the editor is collaborative. Somebody else can type
 * into a file you then click Run on; without the sandbox that would be a stored
 * XSS with a button attached.
 */

const RUNNER_URL = "/api/code/runner";
const IFRAME_ID = "eaios-code-runner";

export type RunLang = "python" | "javascript";

export interface RunEvent {
  /** `out` streams a chunk; `status` narrates loading; `done` ends the run. */
  type: "out" | "status" | "done";
  stream?: "stdout" | "stderr";
  text?: string;
  ok?: boolean;
  ms?: number;
  /** "timeout" | "stopped" when the run was cut short rather than finishing. */
  note?: string | null;
}

/** Map a Monaco language id to a runtime, or null if we cannot run it. */
export function runtimeFor(language: string | undefined | null): RunLang | null {
  if (!language) return null;
  const l = language.toLowerCase();
  if (l === "python") return "python";
  // TypeScript is deliberately absent: running it would need a compile step,
  // and silently executing it as JavaScript would mislead the moment somebody
  // used a type annotation.
  if (l === "javascript") return "javascript";
  return null;
}

let frame: HTMLIFrameElement | null = null;
let ready: Promise<HTMLIFrameElement> | null = null;

/**
 * Mount the sandbox once and keep it. Creating it lazily matters: most people
 * open the Code app to read, and an unused frame would still have paid for the
 * document. Keeping it after the first run matters more — Pyodide stays warm
 * inside it, so the second Python run starts in milliseconds instead of
 * re-downloading the interpreter.
 */
function sandbox(): Promise<HTMLIFrameElement> {
  if (ready) return ready;
  ready = new Promise((resolve, reject) => {
    const el = document.createElement("iframe");
    el.id = IFRAME_ID;
    // allow-scripts WITHOUT allow-same-origin. Granting both together would
    // undo the sandbox entirely — the frame could then reach out and remove
    // its own sandbox attribute.
    el.setAttribute("sandbox", "allow-scripts");
    el.setAttribute("title", "Code execution sandbox");
    el.setAttribute("aria-hidden", "true");
    el.src = RUNNER_URL;
    el.style.cssText = "position:absolute;width:0;height:0;border:0;visibility:hidden";

    const settle = (e: MessageEvent) => {
      if (e.source !== el.contentWindow) return;
      if ((e.data as { type?: string } | undefined)?.type !== "ready") return;
      window.removeEventListener("message", settle);
      clearTimeout(giveUp);
      resolve(el);
    };
    const giveUp = window.setTimeout(() => {
      window.removeEventListener("message", settle);
      ready = null;
      reject(new Error("The code sandbox did not start. Try reloading the page."));
    }, 15_000);

    window.addEventListener("message", settle);
    document.body.appendChild(el);
    frame = el;
  });
  return ready;
}

let active: ((e: RunEvent) => void) | null = null;
let listening = false;

function listen() {
  if (listening) return;
  listening = true;
  window.addEventListener("message", (e: MessageEvent) => {
    // Identity check, not an origin check. The sandbox has an opaque origin, so
    // `e.origin` is the string "null" — which any other opaque context could
    // also claim. Comparing the source *window* is the check that cannot be
    // spoofed by another frame on the page.
    if (!frame || e.source !== frame.contentWindow) return;
    const d = e.data as (RunEvent & { type: string }) | undefined;
    if (!d || (d.type !== "out" && d.type !== "status" && d.type !== "done")) return;
    active?.(d);
  });
}

/**
 * Run `code` in the sandbox, calling `onEvent` as output arrives.
 *
 * Resolves when the run ends — normally, by error, by timeout, or because
 * `stop()` was called. One run at a time: a second call while one is in flight
 * is refused rather than queued, because the console shows a single stream and
 * interleaving two programs into it would be unreadable.
 */
export async function runCode(
  lang: RunLang,
  code: string,
  onEvent: (e: RunEvent) => void,
  /** Shown in Python tracebacks in place of Pyodide's internal "<exec>". */
  filename = "",
  timeoutMs = 10_000,
): Promise<void> {
  if (active) throw new Error("Something is already running.");
  listen();
  const el = await sandbox();

  return new Promise<void>((resolve) => {
    active = (e) => {
      onEvent(e);
      if (e.type === "done") { active = null; resolve(); }
    };
    // targetOrigin "*" is forced by the opaque origin — there is no origin
    // string that would match it. Safe here because what travels outward is
    // only the program's own source, which the sandbox is about to run anyway.
    el.contentWindow?.postMessage(
      { eaios: "run-request", type: "run", lang, code, filename, timeoutMs }, "*");
  });
}

/** Ask the sandbox to terminate the running program. */
export function stopCode() {
  if (!active || !frame) return;
  frame.contentWindow?.postMessage({ eaios: "run-request", type: "stop" }, "*");
}

/** Drop the sandbox — used when the Code app unmounts, so a warm Pyodide
 *  instance is not left holding ~100 MB of heap for a closed window. */
export function disposeSandbox() {
  active = null;
  ready = null;
  frame?.remove();
  frame = null;
}
