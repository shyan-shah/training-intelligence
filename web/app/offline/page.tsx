import type { Metadata } from "next";

export const metadata: Metadata = { title: "Offline" };

/**
 * Shown by the service worker when a navigation fails.
 *
 * Deliberately says there is no cached data rather than implying the app is
 * broken, and renders entirely from server HTML so it works with the JS
 * bundle unavailable.
 */
export default function OfflinePage() {
  return (
    <main
      className="flex min-h-[100dvh] items-center justify-center px-6"
      style={{ background: "var(--plane)" }}
    >
      <div className="panel w-full max-w-sm p-6 text-center">
        <div
          className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full"
          style={{ background: "var(--surface-sunken)", color: "var(--text-muted)" }}
        >
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <path d="M3 3l18 18" />
            <path d="M8.5 16.4a5 5 0 0 1 7 0" />
            <path d="M5 12.9a10 10 0 0 1 3.2-2.1" />
            <path d="M15.8 10.8A10 10 0 0 1 19 12.9" />
            <path d="M2 9.3a15 15 0 0 1 5-3" />
            <path d="M17 6.3a15 15 0 0 1 5 3" />
            <path d="M12 20h.01" />
          </svg>
        </div>

        <h1 className="text-lg font-semibold tracking-tight">No connection</h1>

        <p
          className="mx-auto mt-2 max-w-xs text-xs leading-relaxed"
          style={{ color: "var(--text-secondary)" }}
        >
          Your numbers are not stored on this phone, by design, so there is
          nothing to show until you are back online. The app itself is cached
          and will open the moment you are.
        </p>

        <a
          href="/training"
          className="press mt-5 inline-block w-full rounded-xl px-3 py-2.5 text-sm font-semibold text-white"
          style={{ background: "var(--accent)" }}
        >
          Try again
        </a>
      </div>
    </main>
  );
}
