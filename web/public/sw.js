/*
 * Service worker for Training Intelligence.
 *
 * Hand-written rather than generated, because the caching rules here are a
 * privacy decision and need to be readable.
 *
 * WHAT IS CACHED
 *   /_next/static/*   cache-first, forever. Content-hashed, so a new build
 *                     produces new URLs and the old ones simply fall out.
 *   icons, manifest   cache-first.
 *   /offline          precached at install, so there is something to show.
 *
 * WHAT IS NEVER CACHED
 *   Any navigation response. /training is server-rendered with Shyan's
 *   health data inside the HTML, and next.config.mjs already sends
 *   `Cache-Control: private, no-store` for it. Writing that same HTML into
 *   Cache Storage would put sleep, HRV and body composition on disk in a
 *   place that header exists to prevent, and undo it silently.
 *
 *   /api/*, /auth/*, and every cross-origin request (Supabase included).
 *   Those are either mutations, credentials, or the data itself.
 *
 * WHAT THIS BUYS
 *   The app opens instantly on a slow connection, because the ~103kB of
 *   shared JS and the CSS come off disk rather than the network. Offline it
 *   shows a real screen instead of a white page or Safari's error.
 *
 *   It does NOT give you yesterday's numbers on a plane. That is the
 *   deliberate trade: the shell is cached, the data is not.
 */

const VERSION = "v1";
const STATIC_CACHE = `ti-static-${VERSION}`;
const SHELL_CACHE = `ti-shell-${VERSION}`;
const OFFLINE_URL = "/offline";

const PRECACHE = [
  OFFLINE_URL,
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // Individually, so one 404 does not abort the whole install.
      await Promise.all(
        PRECACHE.map(async (url) => {
          try {
            await cache.add(new Request(url, { cache: "reload" }));
          } catch {
            // A missing optional asset must not stop the worker installing.
          }
        }),
      );
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Navigation preload lets the browser start the network request while
      // the worker boots, so network-first costs nothing on a warm start.
      if (self.registration.navigationPreload) {
        await self.registration.navigationPreload.enable();
      }

      const keep = new Set([STATIC_CACHE, SHELL_CACHE]);
      const names = await caches.keys();
      await Promise.all(names.filter((n) => !keep.has(n)).map((n) => caches.delete(n)));

      await self.clients.claim();
    })(),
  );
});

/** Lets the page tell a waiting worker to take over immediately. */
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

function isStaticAsset(url) {
  return (
    url.pathname.startsWith("/_next/static/") ||
    url.pathname === "/manifest.webmanifest" ||
    /\.(?:png|svg|ico|woff2?|webp|avif)$/.test(url.pathname)
  );
}

function isNeverCached(url) {
  return url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/");
}

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only GET. A POST to /api/checkin must never be served from a cache.
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Cross-origin, Supabase above all, is left entirely alone.
  if (url.origin !== self.location.origin) return;

  if (isNeverCached(url)) return;

  // --- static assets: cache-first ------------------------------------------
  if (isStaticAsset(url)) {
    event.respondWith(
      (async () => {
        const cached = await caches.match(request);
        if (cached) return cached;

        try {
          const response = await fetch(request);
          if (response.ok) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(request, response.clone());
          }
          return response;
        } catch {
          // An asset miss while offline: let it fail rather than invent one.
          return Response.error();
        }
      })(),
    );
    return;
  }

  // --- navigations: network-first, offline page as the fallback ------------
  if (request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const preloaded = await event.preloadResponse;
          if (preloaded) return preloaded;
          return await fetch(request);
        } catch {
          // Offline. Nothing rendered is cached, so this is the whole story.
          const cache = await caches.open(SHELL_CACHE);
          const offline = await cache.match(OFFLINE_URL);
          return (
            offline ??
            new Response("Offline", {
              status: 503,
              headers: { "Content-Type": "text/plain" },
            })
          );
        }
      })(),
    );
  }

  // Everything else falls through to the network untouched.
});
