"""The code runner sandbox — a document whose only job is to be untrusted.

EAIOS does not execute user code on the server. Running arbitrary code on a
shared container is remote code execution by another name, and no amount of
process trickery makes that safe on a free-tier box. So execution happens in
the browser, and this endpoint serves the page it happens inside.

**Why an iframe and not a Web Worker.** A worker would be simpler, but the Code
app is *collaborative*: person B can type code into a shared file that person A
then clicks Run on. A worker is same-origin, so B's code would run with A's
cookies and A's ability to call the API as A. That is a stored XSS with extra
steps. This document is framed with ``sandbox="allow-scripts"`` and
deliberately *without* ``allow-same-origin``, which gives it an **opaque
origin**: no cookies, no localStorage, no reach into the parent DOM, and every
request to the EAIOS API is cross-origin from ``null`` and rejected by CORS.

**Why the CSP below has no ``'self'``.** In an opaque origin ``'self'`` matches
nothing, so it is not merely omitted — it *cannot* be granted. The sandbox is
allowed to load one CDN and nothing else. It can reach Pyodide; it cannot reach
this application. The permissive parts (``unsafe-eval``, ``wasm-unsafe-eval``)
are the price of running code at all, and they are spent inside a context that
has nothing worth stealing.

**Why Pyodide comes from a CDN.** CPython-on-WebAssembly plus the stdlib is
~10 MB; vendoring it would bloat every deploy for a feature most sessions never
open. Loading it into an opaque origin means a compromised CDN gets code
execution in a sandbox with no session and no API access — the same thing it
would get by hosting that code on its own site.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/code", tags=["code"])

# Pinned, not floating. A CDN version range would let an upstream release
# change what runs in the sandbox without a deploy here.
PYODIDE_VERSION = "0.28.3"
PYODIDE_URL = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
_CDN = "https://cdn.jsdelivr.net"

# Wall-clock ceiling enforced inside the sandbox. The parent asks for a limit;
# this is the one the sandbox will not exceed regardless of what it is asked.
MAX_TIMEOUT_MS = 30_000
DEFAULT_TIMEOUT_MS = 10_000
# Fetching ~10 MB of CPython on a bad connection is not a runaway program, so
# waiting for the runtime gets its own, much longer, allowance.
BOOT_TIMEOUT_MS = 90_000
# Output is streamed to the parent, which keeps a bounded buffer, but a tight
# print loop can flood postMessage faster than React can render. Cap here too.
MAX_OUTPUT_CHARS = 200_000

SANDBOX_CSP = "; ".join([
    "default-src 'none'",
    # No 'self': in an opaque origin it matches nothing anyway. The sandbox may
    # execute code and load exactly one CDN.
    f"script-src 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' {_CDN} blob:",
    f"connect-src {_CDN} blob: data:",
    "worker-src blob:",                 # execution happens in a terminable worker
    "child-src blob:",                  # older browsers spell it this way
    "style-src 'unsafe-inline'",
    "img-src data: blob:",
    "form-action 'none'",
    "base-uri 'none'",
    "frame-ancestors 'self'",           # only EAIOS may embed this
])

# ── the worker: where the code actually runs ──────────────────────────────
# A separate thread so a runaway loop cannot freeze the editor, and — the
# reason it is a worker rather than inline — so it can be terminated. There is
# no cooperative way to stop `while True: pass`; terminate() is the only one.
_WORKER_JS = r"""
'use strict';
var PYODIDE_URL = "__PYODIDE_URL__";
var MAX_OUTPUT = __MAX_OUTPUT__;
var pyodide = null, emitted = 0, truncated = false;

function out(stream, text) {
  if (truncated) return;
  text = String(text);
  if (emitted + text.length > MAX_OUTPUT) {
    text = text.slice(0, Math.max(0, MAX_OUTPUT - emitted));
    truncated = true;
  }
  emitted += text.length;
  if (text) postMessage({ type: "out", stream: stream, text: text });
  if (truncated) postMessage({ type: "out", stream: "stderr",
                               text: "\n… output truncated (limit reached).\n" });
}
function status(text) { postMessage({ type: "status", text: text }); }

/* console.log(obj) printing "[object Object]" is the single most annoying
   thing about naive capture, so objects are formatted rather than coerced. */
function fmt(v) {
  if (typeof v === "string") return v;
  if (v instanceof Error) return (v.stack || String(v));
  if (v === undefined) return "undefined";
  if (v === null) return "null";
  if (typeof v === "function") return v.toString();
  try {
    var seen = new WeakSet();
    return JSON.stringify(v, function (k, x) {
      if (typeof x === "object" && x !== null) {
        if (seen.has(x)) return "[Circular]";
        seen.add(x);
      }
      if (typeof x === "bigint") return String(x) + "n";
      return x;
    }, 2);
  } catch (e) { return String(v); }
}
function join(args) { return Array.prototype.map.call(args, fmt).join(" "); }

var SANDBOX_CONSOLE = {
  log:   function () { out("stdout", join(arguments) + "\n"); },
  info:  function () { out("stdout", join(arguments) + "\n"); },
  debug: function () { out("stdout", join(arguments) + "\n"); },
  table: function () { out("stdout", join(arguments) + "\n"); },
  dir:   function () { out("stdout", join(arguments) + "\n"); },
  warn:  function () { out("stderr", join(arguments) + "\n"); },
  error: function () { out("stderr", join(arguments) + "\n"); },
  trace: function () { out("stderr", join(arguments) + "\n"); },
  assert: function (ok) {
    if (!ok) out("stderr", "Assertion failed: " +
                 join(Array.prototype.slice.call(arguments, 1)) + "\n");
  },
  group: function () { out("stdout", join(arguments) + "\n"); },
  groupEnd: function () {},
  time: function () {}, timeEnd: function () {}, count: function () {},
};
try { self.console = SANDBOX_CONSOLE; } catch (e) { /* frozen in some engines */ }

/* AsyncFunction, so top-level `await` works the way people expect in a REPL. */
var AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

/* Pyodide runs the code through its own eval_code_async, so a raw traceback
   opens with two frames inside /lib/python313.zip/_pyodide/_base.py before it
   ever reaches the person's code. Someone learning Python reads that as "the
   error is in a file I have never heard of". Everything above the first
   <exec> frame is our plumbing, so it goes; what is left is the traceback
   they would have got from `python main.py`. */
function trimPythonTraceback(text, filename) {
  var lines = text.split("\n");
  var first = -1;
  for (var i = 0; i < lines.length; i++) {
    if (lines[i].indexOf('File "<exec>"') !== -1) { first = i; break; }
  }
  if (first === -1) return text;              /* unfamiliar shape — leave it alone */
  var head = lines[0].indexOf("Traceback") === 0 ? [lines[0]] : [];
  return head.concat(lines.slice(first)).join("\n")
             .split('"<exec>"').join('"' + (filename || "your code") + '"');
}

async function runJS(code) {
  postMessage({ type: "exec" });   /* nothing to download; start the clock now */
  /* `console` is passed as a parameter as well as set globally: the parameter
     shadows any later reassignment and is captured by closures inside the
     user's code, so a console.log inside a setTimeout still lands here. */
  var fn = null;
  /* A function body does not return its last expression, so `40 + 2` on its
     own would print nothing — which looks broken, because Python's runner
     *does* print it. Compiling as an expression first and falling back on a
     SyntaxError is how browser devtools resolve the same ambiguity: `1 + 1`
     is an expression, `let x = 1` is not, and only the parser knows which. */
  try { fn = new AsyncFunction("console", "return (\n" + code + "\n);"); }
  catch (e) { fn = null; }
  if (!fn) fn = new AsyncFunction("console", code);   /* real errors surface here */

  var value = await fn(SANDBOX_CONSOLE);
  if (value !== undefined) out("stdout", fmt(value) + "\n");
}

async function runPython(code) {
  if (!pyodide) {
    status("Downloading Python runtime (first run only)…");
    importScripts(PYODIDE_URL + "pyodide.js");
    pyodide = await loadPyodide({
      indexURL: PYODIDE_URL,
      stdout: function (line) { out("stdout", line + "\n"); },
      stderr: function (line) { out("stderr", line + "\n"); },
    });
  }
  /* `import numpy` should work without the person hunting for an install
     button, so imports are resolved against the packages Pyodide ships. A
     name it does not know is left alone: Python's own ImportError is a better
     error message than anything invented here. */
  try {
    status("Resolving imports…");
    await pyodide.loadPackagesFromImports(code);
  } catch (e) { /* fall through and let Python report it */ }
  status("");
  /* Everything above is download time, not the program's time. Tell the
     supervisor the clock starts now, otherwise a cold first run would look
     like a ten-second infinite loop and get killed before printing a line. */
  postMessage({ type: "exec" });

  /* A fresh namespace per run. The interpreter stays warm (a second run is
     instant) but leftover variables from the last run cannot silently make
     broken code look like it works. */
  /* toPy({}) rather than the globals.get("dict") idiom from the docs: `dict`
     is a builtin, not a key in __main__'s globals, so that lookup is one
     Pyodide internal away from returning undefined. CPython inserts
     __builtins__ into any globals dict it is handed, so an empty one is a
     complete namespace. */
  var ns = pyodide.toPy({});
  try {
    var value = await pyodide.runPythonAsync(code, { globals: ns });
    if (value !== undefined && value !== null) {
      out("stdout", (value && value.toString ? value.toString() : String(value)) + "\n");
      if (value && typeof value.destroy === "function") value.destroy();
    }
  } finally { ns.destroy(); }
}

onmessage = async function (e) {
  var d = e.data || {};
  emitted = 0; truncated = false;
  var t0 = (self.performance && performance.now) ? performance.now() : Date.now();
  var elapsed = function () {
    var t1 = (self.performance && performance.now) ? performance.now() : Date.now();
    return Math.round(t1 - t0);
  };
  try {
    if (d.lang === "python") await runPython(d.code);
    else await runJS(d.code);
    postMessage({ type: "done", ok: true, ms: elapsed() });
  } catch (err) {
    /* Pyodide puts the whole Python traceback on .message — far more useful
       than the JS stack wrapping it, so message wins when both exist. The JS
       stack is deliberately dropped: every frame in it belongs to this
       harness, not to the person's code, so it is noise pointing at the
       wrong file. The error's own name is kept, because "TypeError: x is not
       a function" says more than "x is not a function". */
    var text = String((err && err.message) ? err.message
                    : (err && err.stack) ? err.stack : err);
    if (text.indexOf("Traceback (most recent call last)") === 0) {
      /* Python: the traceback already names the error; prefixing it with the
         JS wrapper's "PythonError:" would just bury the real one. */
      text = trimPythonTraceback(text, d.filename);
    } else if (err && err.name && text.indexOf(err.name) !== 0) {
      text = err.name + ": " + text;
    }
    out("stderr", text.replace(/\s+$/, "") + "\n");
    postMessage({ type: "done", ok: false, ms: elapsed() });
  }
};

/* An unhandled rejection inside user code would otherwise vanish silently. */
self.onunhandledrejection = function (e) {
  out("stderr", "Unhandled promise rejection: " + fmt(e.reason) + "\n");
};
"""

# ── the sandbox document: supervisor for the worker ───────────────────────
_RUNNER_HTML = r"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>EAIOS code runner</title></head>
<body>
<script>
(function () {
  'use strict';
  var MAX_TIMEOUT = __MAX_TIMEOUT__;
  var DEFAULT_TIMEOUT = __DEFAULT_TIMEOUT__;
  var BOOT_TIMEOUT = __BOOT_TIMEOUT__;
  var WORKER_SRC = __WORKER_SRC__;

  var blobUrl = URL.createObjectURL(new Blob([WORKER_SRC], { type: "text/javascript" }));
  var worker = null, timer = null, running = false, startedAt = 0, limitMs = 0;

  /* targetOrigin is "*" because this document has an opaque origin and cannot
     name the parent's. That is safe in this direction: nothing secret travels
     outward — only the program's own stdout — and the parent verifies the
     sender is this frame before believing any of it. */
  function post(msg) { parent.postMessage(msg, "*"); }

  function spawn() {
    var w = new Worker(blobUrl);
    w.onmessage = function (e) {
      var d = e.data || {};
      if (d.type === "done") finish(d.ok, d.ms, null);
      else if (d.type === "exec") arm(limitMs, runMsg);  /* runtime is up */
      else post(d);
    };
    w.onerror = function (e) {
      post({ type: "out", stream: "stderr",
             text: (e && e.message ? e.message : "The runtime crashed.") + "\n" });
      /* An onerror means the worker is not trustworthy any more: drop it so
         the next run gets a clean one rather than inheriting a broken heap. */
      try { w.terminate(); } catch (_) {}
      if (worker === w) worker = null;
      finish(false, Date.now() - startedAt, null);
    };
    return w;
  }

  function finish(ok, ms, note) {
    if (!running) return;
    running = false;
    if (timer) { clearTimeout(timer); timer = null; }
    post({ type: "done", ok: ok, ms: ms, note: note });
  }

  function halt(note) {
    /* terminate() is why execution lives in a worker: an infinite loop has no
       cooperative exit, and this is the only thing that stops one. */
    if (worker) { try { worker.terminate(); } catch (_) {} worker = null; }
    finish(false, Date.now() - startedAt, note);
  }

  /* (Re)start the execution clock. Called once when a run is dispatched and
     again if the worker reports that its runtime has finished loading, so a
     cold Pyodide download is not counted against the program's time limit. */
  function arm(ms, why) {
    if (!running) return;
    if (timer) clearTimeout(timer);
    startedAt = Date.now();
    timer = setTimeout(function () {
      post({ type: "out", stream: "stderr", text: "\n" + why(ms) + "\n" });
      halt("timeout");
    }, ms);
  }
  function bootMsg(ms) {
    return "Gave up after " + Math.round(ms / 1000) +
           "s waiting for the runtime to load — check the network connection.";
  }
  function runMsg(ms) {
    return "Stopped after " + Math.round(ms / 1000) +
           "s — the program was still running.";
  }

  function run(d) {
    if (running) return;
    limitMs = Math.min(Math.max(1000, d.timeoutMs || DEFAULT_TIMEOUT), MAX_TIMEOUT);
    running = true;
    if (!worker) worker = spawn();
    /* Two clocks, not one. Downloading 10 MB of CPython over a slow link is
       not the program taking too long, and charging it against a ten-second
       execution limit would kill every first Python run. The generous boot
       clock runs until the worker says the code itself has started. */
    arm(BOOT_TIMEOUT, bootMsg);
    worker.postMessage({ lang: d.lang, filename: String(d.filename || ""),
                         code: String(d.code == null ? "" : d.code) });
  }

  addEventListener("message", function (e) {
    /* Only the embedder gets to drive this. */
    if (e.source !== parent) return;
    var d = e.data;
    if (!d || d.eaios !== "run-request") return;
    if (d.type === "run") run(d);
    else if (d.type === "stop") {
      post({ type: "out", stream: "stderr", text: "\nStopped.\n" });
      halt("stopped");
    }
  });

  post({ type: "ready" });
})();
</script>
</body>
</html>
"""


def runner_html() -> str:
    """The sandbox document, with the worker source inlined as a JS string."""
    import json

    worker_src = (_WORKER_JS
                  .replace("__PYODIDE_URL__", PYODIDE_URL)
                  .replace("__MAX_OUTPUT__", str(MAX_OUTPUT_CHARS)))
    # json.dumps handles every quote, backslash and newline correctly. The one
    # thing it does not do is protect against "</script>" appearing inside the
    # string, which an HTML parser would honour and use to end the block early.
    # The worker contains none today; escaping it means a future edit that adds
    # one cannot quietly turn this page into an injection point.
    literal = json.dumps(worker_src).replace("</", "<\\/")
    return (_RUNNER_HTML
            .replace("__MAX_TIMEOUT__", str(MAX_TIMEOUT_MS))
            .replace("__DEFAULT_TIMEOUT__", str(DEFAULT_TIMEOUT_MS))
            .replace("__BOOT_TIMEOUT__", str(BOOT_TIMEOUT_MS))
            .replace("__WORKER_SRC__", literal))


@router.get("/runner", include_in_schema=False)
def code_runner() -> HTMLResponse:
    """Serve the execution sandbox.

    Unauthenticated on purpose: the document contains no workspace data and
    reads none. Requiring a session would buy nothing — the page is a static
    shell, and everything interesting is posted into it by the parent frame,
    which *is* authenticated.
    """
    return HTMLResponse(
        runner_html(),
        headers={
            "Content-Security-Policy": SANDBOX_CSP,
            # The app's default is DENY, which would stop it framing its own
            # sandbox. SAMEORIGIN plus frame-ancestors 'self' is the pair that
            # lets EAIOS embed this and nobody else.
            "X-Frame-Options": "SAMEORIGIN",
            "Cache-Control": "public, max-age=600",
            "X-Robots-Tag": "noindex",
        },
    )
