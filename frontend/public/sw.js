/* EAIOS service worker — offline app shell (PWA).
   Strategy: network-first for /api (freshness), cache-first for the shell
   and static assets. Demo mode already works with no backend, so a cached
   shell means the whole OS runs offline. */
const CACHE = "eaios-shell-v2";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/eaios-icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  if (url.pathname.startsWith("/api")) {
    // network-first, no caching of API data (auth-sensitive)
    return;
  }

  e.respondWith(
    caches.match(e.request).then((hit) => {
      const fetched = fetch(e.request)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then((c) => c.put(e.request, clone));
          }
          return res;
        })
        .catch(() => hit);
      return hit || fetched;
    })
  );
});
