const CACHE = "field-metrics-v1";
const ASSETS = [
  "/metrics",
  "/metrics/log",
  "/metrics/start",
  "/metrics/summary",
  "/metrics/report",
  "/static/css/app.css",
  "/static/css/field-metrics.css",
  "/static/js/metrics/storage.js",
  "/static/js/metrics/validate-client.js",
  "/static/js/metrics/aggregate-client.js",
  "/static/js/metrics/log.js",
  "/static/js/metrics/start.js",
  "/static/js/metrics/summary.js",
  "/static/js/metrics/report.js",
  "/static/js/metrics/pwa.js",
  "/static/js/metrics/nav.js",
  "/static/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (!url.pathname.startsWith("/metrics") && !url.pathname.startsWith("/static/")) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (!response || response.status !== 200) return response;
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        return response;
      }).catch(() => cached);
    }),
  );
});
