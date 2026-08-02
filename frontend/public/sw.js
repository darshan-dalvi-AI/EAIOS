/* K-OS service worker — offline app shell (PWA).
   v3 — network-first for the HTML shell so every deploy goes live on the next
   load (cache only serves offline). Cache-first stays for hashed immutable
   assets. v2's cache-first-everything served stale bundles after deploys,
   which could mix old and new code ("n is not a function" crashes). */
// Bumped for the K-OS mark. The old cache holds the previous manifest and
// icon, and the activate handler deletes every cache whose name is not this
// one — so renaming is what actually gets the new icon onto installed copies.
// Replaced at build time by the stamp-service-worker plugin in vite.config.ts.
//
// This line is load-bearing, and not only for the cache name. A browser decides
// there is a new worker by byte-comparing the fetched /sw.js against the
// installed one — so while this file was a fixed string, a deploy that changed
// every application chunk but not the worker was invisible: no update event,
// no prompt, and the old bundle kept serving. Stamping the build in guarantees
// the file differs on every deploy, which is what makes the update detectable
// at all. It also retires the hand-bumped "-v4" suffix that had to be
// remembered.
const BUILD = "__SW_BUILD__";
const CACHE = "k-os-shell-" + BUILD;
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/k-os-icon.svg"];

// NOTE: no skipWaiting() here, deliberately.
//
// v4 called it, so a new deploy seized control the moment it finished
// installing and the page reloaded itself underneath whoever was using it —
// mid-sentence in a chat, mid-edit in the Code app. Now a new version installs
// and *parks* in the waiting state; the app notices, says so, and only takes
// over when the person clicks Reload (lib/updates.ts posts SKIP_WAITING).
//
// This costs nothing on a first install: with no worker already in control
// there is no waiting phase at all, so the shell still activates immediately.
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => null));
});

// The page asking to be updated now.
self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Vite emits content-hashed filenames under /assets — immutable by definition.
const isHashedAsset = (path) => /^\/assets\/.+[-.][A-Za-z0-9_-]{8,}\.(js|css|woff2?|svg|png|jpg)$/.test(path);

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api")) return; // network only — auth-sensitive

  // The app shell: NETWORK-FIRST. A fresh deploy is picked up immediately;
  // the cached copy is only used when the network is gone (true offline).
  if (e.request.mode === "navigate" || url.pathname === "/" || url.pathname.endsWith("/index.html")) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          if (res.ok) { const clone = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, clone)); }
          return res;
        })
        .catch(() => caches.match(e.request).then((hit) => hit || caches.match("/index.html")))
    );
    return;
  }

  // Hashed build assets never change content for a given name → cache-first.
  if (isHashedAsset(url.pathname)) {
    e.respondWith(
      caches.match(e.request).then((hit) =>
        hit ||
        fetch(e.request).then((res) => {
          if (res.ok) { const clone = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, clone)); }
          return res;
        })
      )
    );
    return;
  }

  // Everything else (manifest, icons): stale-while-revalidate.
  e.respondWith(
    caches.match(e.request).then((hit) => {
      const fetched = fetch(e.request)
        .then((res) => {
          if (res.ok) { const clone = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, clone)); }
          return res;
        })
        .catch(() => hit);
      return hit || fetched;
    })
  );
});
