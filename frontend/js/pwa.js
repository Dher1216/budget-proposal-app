// Home-screen / instant-open support. Loaded on every page (after api.js).
//  1. Registers the service worker (/sw.js) that keeps the app's own screens
//     on the device so it opens instantly, even while the server is asleep.
//  2. Shows a friendly "server is waking up" message if the first request to
//     the server takes more than 4 seconds.
//  3. Shows an "Install" banner on phones (never on desktop or once installed).
// Kept in its own file (no inline script) so it works under a strict
// same-origin Content Security Policy.

// ---------------------------------------------------------------- 1. service worker
if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    try {
      // Remove the old /app/-scoped registration from earlier versions so only
      // the site-wide one remains.
      const regs = await navigator.serviceWorker.getRegistrations();
      for (const reg of regs) {
        if (reg.scope.endsWith("/app/")) await reg.unregister();
      }
    } catch (e) { /* not fatal */ }
    try {
      const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      reg.update().catch(() => {});
    } catch (e) {
      // Not fatal -- the app still works online.
    }
  });
}

// ---------------------------------------------------------------- 2. waking-up message
(function () {
  if (!window.fetch) return;
  // Never over the sign-in screen.
  if (document.getElementById("loginForm")) return;

  const WAKING_AFTER_MS = 4000;
  const originalFetch = window.fetch.bind(window);
  let watching = false;
  let timer = null;
  let notice = null;

  function isApiRequest(input) {
    try {
      const raw = typeof input === "string" ? input : (input && input.url) || "";
      const u = new URL(raw, window.location.href);
      return u.origin === window.location.origin && u.pathname.startsWith("/api/");
    } catch (e) { return false; }
  }

  function showNotice() {
    timer = null;
    if (notice || !document.body) return;
    notice = document.createElement("div");
    notice.className = "waking-notice";
    notice.setAttribute("role", "status");
    notice.innerHTML =
      '<span class="waking-spinner" aria-hidden="true"></span>' +
      '<div><strong>Opening the app.</strong> The server is waking up. ' +
      'This can take up to a minute the first time. Please wait.</div>';
    document.body.appendChild(notice);
  }

  function finish() {
    if (timer) { clearTimeout(timer); timer = null; }
    if (notice) { notice.remove(); notice = null; }
  }

  window.fetch = function (input, init) {
    const promise = originalFetch(input, init);
    // Only the FIRST request to the server is watched.
    if (!watching && isApiRequest(input)) {
      watching = true;
      timer = setTimeout(showNotice, WAKING_AFTER_MS);
      promise.then(finish, finish); // success or failure -- either way, stop
    }
    return promise;
  };
})();

// ---------------------------------------------------------------- 3. install banner
(function () {
  const ua = navigator.userAgent || "";
  const isIOS = /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/.test(ua);
  if (!isIOS && !isAndroid) return; // phones/tablets only, never desktop

  const standalone =
    (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
    window.navigator.standalone === true;
  if (standalone) return; // already installed

  const DISMISS_KEY = "pwa_install_dismissed";
  function wasDismissed() {
    try { return localStorage.getItem(DISMISS_KEY) === "1"; } catch (e) { return false; }
  }
  function rememberDismissed() {
    try { localStorage.setItem(DISMISS_KEY, "1"); } catch (e) { /* ignore */ }
  }
  if (wasDismissed()) return;

  const APP_NAME = "Budget Proposal System";
  let banner = null;
  let deferredPrompt = null;

  function removeBanner() {
    if (banner) { banner.remove(); banner = null; }
  }

  function buildBanner(bodyHtml, withInstallButton) {
    if (banner || !document.body) return;
    banner = document.createElement("div");
    banner.className = "install-banner no-print";
    banner.setAttribute("role", "dialog");
    banner.setAttribute("aria-label", "Install " + APP_NAME);
    banner.innerHTML =
      '<img class="install-banner-icon" src="/app/icons/icon-192.png" alt="" width="40" height="40">' +
      '<div class="install-banner-text"><strong>Install ' + APP_NAME + '</strong>' + bodyHtml + '</div>' +
      '<div class="install-banner-actions">' +
        (withInstallButton ? '<button type="button" class="btn install-banner-install">Install</button>' : "") +
        '<button type="button" class="btn secondary install-banner-dismiss">Not now</button>' +
      '</div>';
    document.body.appendChild(banner);

    banner.querySelector(".install-banner-dismiss").addEventListener("click", () => {
      rememberDismissed();
      removeBanner();
    });
    const installBtn = banner.querySelector(".install-banner-install");
    if (installBtn) {
      installBtn.addEventListener("click", async () => {
        if (!deferredPrompt) return;
        const promptEvent = deferredPrompt;
        deferredPrompt = null;
        removeBanner();
        try {
          promptEvent.prompt();
          await promptEvent.userChoice;
        } catch (e) { /* ignore */ }
      });
    }
  }

  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    removeBanner();
  });

  if (isAndroid) {
    // Chrome on Android: hold the browser's install prompt until the button is tapped.
    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      deferredPrompt = e;
      buildBanner("", true);
    });
  } else {
    // iPhone / iPad: there is no install prompt -- only show instructions, in Safari.
    const isSafari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
    if (!isSafari) return;
    setTimeout(() => {
      if (wasDismissed()) return;
      buildBanner('<div>In Safari, tap the Share button, then Add to Home Screen</div>', false);
    }, 2500);
  }
})();
