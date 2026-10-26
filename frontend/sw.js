// Service worker: keeps the app's own screens (HTML, CSS, JS, icons) on the
// device so the app opens instantly -- even while the free Render server is
// asleep -- instead of showing Render's "waking up" page. The app then shows
// its own friendly message and loads the data once the server answers.
//
// Strategy: stale-while-revalidate. A page/file is answered from the saved
// copy at once, and refreshed from the network in the background so the next
// open has the latest version. If there is no saved copy, it goes to the
// network.
//
// NEVER handled here (always goes straight to the server, untouched):
//   - anything under /api/ (all data, sign-in, session, attachments, logos)
//   - any non-GET request
//   - any other website's requests
//   - /docs, /openapi.json and anything else that isn't an app screen/file
// Budget figures are therefore never saved by this service worker.
//
// CACHE VERSION: the placeholder below is replaced by the server with a
// fingerprint of the frontend files every time /sw.js is requested, so any
// code change automatically produces a new cache version -- no manual
// bumping. (If the placeholder is left as-is, e.g. when opened directly from
// disk, it falls back to "dev".)
const BUILD = "__BUILD_VERSION__";
const CACHE_VERSION = BUILD.startsWith("__") ? "dev" : BUILD;
const CACHE_PREFIX = "budget-app-shell-";
const CACHE_NAME = `${CACHE_PREFIX}v${CACHE_VERSION}`;

// Every file the app needs to open (stored without the ?v= query string --
// lookups ignore it, so old/new HTML references both find the right file).
const APP_SHELL_URLS = [
  "/app/",
  "/app/index.html",
  "/app/admin.html",
  "/app/client.html",
  "/app/css/app.css",
  "/app/js/api.js",
  "/app/js/pwa.js",
  "/app/js/admin.js",
  "/app/js/client.js",
  "/app/icons/icon-192.png",
  "/app/icons/icon-512.png",
  "/app/icons/apple-touch-icon.png",
  "/app/icons/favicon-32.png",
  "/manifest.webmanifest",
];
const SHELL_PATHS = new Set(APP_SHELL_URLS);
const STATIC_EXT = /\.(?:html|css|js|png|jpg|jpeg|svg|ico|webp|gif|woff2?|ttf|otf|webmanifest)$/i;

function isShellPath(pathname) {
  if (SHELL_PATHS.has(pathname)) return true;
  return pathname.startsWith("/app/") && STATIC_EXT.test(pathname);
}

// Cache key = the path only, so "?v=..." changes never create duplicates.
function cacheKeyFor(url) {
  return new Request(url.origin + url.pathname);
}

// Only keep responses that really are the app's files -- never an error
// page, and never a hosting provider's "waking up" interstitial that could
// come back with a 200 while the server is starting.
async function isGoodResponse(response, pathname) {
  if (!response || response.status !== 200 || response.type === "opaque") return false;
  const type = response.headers.get("content-type") || "";
  if (/text\/html/i.test(type)) {
    if (!pathname.startsWith("/app/")) return false;
    const text = await response.clone().text();
    return text.includes("css/app.css");
  }
  return true;
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await Promise.all(APP_SHELL_URLS.map(async (path) => {
      // cache: "reload" bypasses the browser's HTTP cache so a fresh copy is saved
      const response = await fetch(new Request(path, { cache: "reload" }));
      if (!(await isGoodResponse(response, path))) throw new Error("Could not cache " + path);
      await cache.put(new Request(self.location.origin + path), response);
    }));
  })());
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names
        .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
        .map((name) => caches.delete(name))
    );
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  const path = url.pathname;
  if (path.startsWith("/api/") || path === "/sw.js") return;

  // Typing the bare address ("/") or "/app" normally needs the server just
  // to be redirected to "/app/". Do that redirect here instead, so even those
  // never touch a sleeping server.
  if (request.mode === "navigate" && (path === "/" || path === "/app")) {
    event.respondWith(Response.redirect(new URL("/app/", url.origin).toString(), 302));
    return;
  }

  if (!isShellPath(path)) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const key = cacheKeyFor(url);
    const cached = await cache.match(key);

    const refresh = fetch(request, { cache: "no-cache" })
      .then(async (response) => {
        if (await isGoodResponse(response, path)) await cache.put(key, response.clone());
        return response;
      });

    if (cached) {
      event.waitUntil(refresh.catch(() => {})); // update quietly for next time
      return cached;
    }
    return refresh; // nothing saved yet: go to the network
  })());
});
