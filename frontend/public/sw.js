/* EAIOS service worker — offline app shell (PWA).
   v3 — network-first for the HTML shell so every deploy goes live on the next
   load (cache only serves offline). Cache-first stays for hashed immutable
   assets. v2's cache-first-everything served stale bundles after deploys,
   which could mix old and new code ("n is not a function" crashes). */
const CACHE = "eaios-shell-v3";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/eaios-icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => null).then(() => self.skipWaiting())
  );
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
