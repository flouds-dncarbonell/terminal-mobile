const CACHE = "terminal-local-v34";
const SHELL = [
  "/",
  "/assets/style.css",
  "/assets/app.js",
  "/assets/files.js",
  "/assets/attachments.js",
  "/assets/vendor/marked.min.js",
  "/assets/vendor/purify.min.js",
  "/assets/vendor/xterm.js",
  "/assets/vendor/xterm.css",
  "/assets/vendor/addon-fit.js",
  "/assets/vendor/mono.ttf",
  "/assets/vendor/display.ttf",
  "/assets/icon-192.png",
  "/assets/icon-512.png",
  "/manifest.webmanifest",
];
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) =>
        cache.addAll(
          SHELL.map((path) => new Request(path, { cache: "reload" })),
        ),
      )
      .then(() => self.skipWaiting()),
  );
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (
    event.request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/terminal/") ||
    url.pathname === "/ca.crt"
  )
    return;
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match("/")));
    return;
  }
  // Network first: the computer is on the LAN, so a fresh copy is cheap and an
  // update shows on the first reload. The cache only covers offline use.
  if (SHELL.includes(url.pathname)) {
    event.respondWith(
      fetch(event.request, { cache: "no-cache" })
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(url.pathname, copy));
          }
          return response;
        })
        .catch(() => caches.match(event.request, { ignoreSearch: true })),
    );
  }
});
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data.json();
  } catch {}
  // The conversation continued elsewhere: drop the stale notification.
  if (data.type === "clear") {
    event.waitUntil(
      self.registration.getNotifications().then((shown) =>
        shown.filter((n) => data.tags.includes(n.tag)).forEach((n) => n.close()),
      ),
    );
    return;
  }
  // Never show an empty card (an unknown or older message format).
  if (!data.title) return;
  event.waitUntil(
    self.registration.showNotification(data.title || "Terminais", {
      body: data.body || "",
      tag: data.tag || undefined,
      lang: "pt-BR",
      renotify: Boolean(data.tag),
      icon: data.icon || "/assets/icon-192.png",
      // Status bar icon: Android uses only the alpha channel.
      badge: "/assets/notify-badge.png",
      timestamp: Date.now(),
      data: { url: data.url || "/" },
    }),
  );
});
// Reuse an open panel when there is one; it moves to the agent's tab.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin);
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windows) => {
        const open = windows.find((client) => new URL(client.url).origin === url.origin);
        if (!open) return self.clients.openWindow(url.href);
        open.postMessage({ type: "open", url: url.href });
        return open.focus();
      }),
  );
});
