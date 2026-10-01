// Service worker: caches the APP'S OWN FILES (HTML/CSS/JS) so the pages
// themselves can load with no internet connection at all -- including after
// a laptop restart or the browser being fully closed and reopened offline.
//
// This is separate from, and doesn't interfere with, the data-layer offline
// handling already in js/api.js (the IndexedDB write-queue and attachment
// cache) -- this file only ever touches the app's static files, never API
// calls under /api/.
//
// IMPORTANT: CACHE_VERSION below must be bumped to match the ?v=... query
// string used on the asset URLs in index.html/admin.html/client.html every
// time those are updated, so offline users pick up the new version the
// next time they're online, instead of being stuck on a stale cached copy.
const CACHE_VERSION = "20261008";
const CACHE_NAME = `budget-app-shell-v${CACHE_VERSION}`;

const APP_SHELL_URLS = [
  "/app/",
  "/app/index.html",
  "/app/admin.html",
  "/app/client.html",
  `/app/css/app.css?v=${CACHE_VERSION}`,
  `/app/js/api.js?v=${CACHE_VERSION}`,
  `/app/js/admin.js?v=${CACHE_VERSION}`,
  `/app/js/client.js?v=${CACHE_VERSION}`,
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) => name.startsWith("budget-app-shell-") && name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;

  // The bare site root ("/") normally 307-redirects to "/app/" -- but that
  // redirect can't be followed with no network connection at all. When
  // offline, synthesize the SAME redirect ourselves (this needs no network
  // or cache lookup -- it's just constructing a response), and the browser
  // will then request "/app/" itself, which IS handled below from cache.
  // (Serving /app/'s cached content directly as the body for "/" would
  // break its relative css/js links, since the browser would resolve them
  // against the wrong base URL -- redirecting avoids that.)
  if (url.pathname === "/") {
    event.respondWith(
      fetch(event.request).catch(() =>
        Response.redirect(new URL("/app/", url.origin).toString(), 302)
      )
    );
    return;
  }

  // Only handle GET requests for this app's own static files, under /app/.
  // Everything else (API calls under /api/, anything else) passes straight
  // through to the network untouched.
  const isAppShellRequest =
    url.pathname.startsWith("/app/") &&
    (url.pathname === "/app/" ||
      url.pathname.endsWith(".html") ||
      url.pathname.endsWith(".css") ||
      url.pathname.endsWith(".js"));

  if (!isAppShellRequest) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => cached); // offline and not already cached -- nothing more we can do
    })
  );
});
