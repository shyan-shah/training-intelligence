"use client";

import { useEffect } from "react";

/**
 * Registers the service worker, in production only.
 *
 * Skipped in development because a cache-first worker sitting in front of a
 * dev server serves yesterday's chunks and wastes an afternoon.
 */
export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;

    const register = () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(
        (reg) => {
          // If a new worker is already waiting, let it take over rather than
          // sitting behind the old one until every tab is closed.
          if (reg.waiting) reg.waiting.postMessage("SKIP_WAITING");

          reg.addEventListener("updatefound", () => {
            const next = reg.installing;
            if (!next) return;
            next.addEventListener("statechange", () => {
              if (next.state === "installed" && navigator.serviceWorker.controller) {
                next.postMessage("SKIP_WAITING");
              }
            });
          });
        },
        () => {
          // Registration failing is not worth breaking the page over: the app
          // works fine without a worker, it just loses the offline screen.
        },
      );
    };

    // After load, so registration never competes with the first render.
    if (document.readyState === "complete") register();
    else window.addEventListener("load", register, { once: true });
  }, []);

  return null;
}
