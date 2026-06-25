// FluxPark service worker.
//
// FluxPark is a server-rendered, session-based, multi-tenant app -- there is
// no realistic way to make per-user dashboards/forms work fully offline
// without a major architecture change. What this *does* provide honestly:
//   - static assets (CSS/JS/fonts/icons) are cached so repeat visits and
//     low-bandwidth connections don't re-download them every time
//   - page navigations try the network first (so you always see live data
//     when online) and fall back to a friendly offline page instead of the
//     browser's default error when there truly is no connection

const STATIC_CACHE = "fluxpark-static-v1";
const PAGE_CACHE = "fluxpark-pages-v1";

// Personalized GET pages that are safe and useful to show from cache when
// offline (no CSRF tokens, no payment/financial detail). Cached network-first
// so you always see live data when online -- the cache is only ever a
// fallback for "no connection at all", refreshed on every successful visit.
const CACHEABLE_PAGES = [
  "/dashboard",
  "/parking-map",
  "/parking-slots",
  "/notifications",
  "/my-profile",
  "/my-rooms",
];

const STATIC_ASSETS = [
  "/static/css/style.css",
  "/static/js/main.js",
  "/static/vendor/bootstrap/css/bootstrap.min.css",
  "/static/vendor/bootstrap/js/bootstrap.bundle.min.js",
  "/static/vendor/bootstrap-icons/bootstrap-icons.min.css",
  "/static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff2",
  "/static/vendor/html5-qrcode/html5-qrcode.min.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/offline.html",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

const CURRENT_CACHES = [STATIC_CACHE, PAGE_CACHE];

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => !CURRENT_CACHES.includes(key)).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Static assets: cache-first, refresh the cache in the background.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((response) => {
            if (response.ok) {
              caches.open(STATIC_CACHE).then((cache) => cache.put(request, response.clone()));
            }
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
    return;
  }

  // Allowlisted personalized pages: network-first, falling back to the last
  // cached copy of that exact page (not the generic offline page) when
  // there's truly no connection.
  if (request.mode === "navigate" && CACHEABLE_PAGES.includes(url.pathname)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            caches.open(PAGE_CACHE).then((cache) => cache.put(request, response.clone()));
          }
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match("/static/offline.html")))
    );
    return;
  }

  // Everything else: network-first, generic offline-page fallback.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/static/offline.html"))
    );
  }
});
