"use client";

import { useEffect, useState } from "react";

import { IconMoon, IconSun } from "./Icons";

type Mode = "light" | "dark" | "system";
const KEY = "ti-theme";

/**
 * Light / dark / system. The palette declares its dark values under both a
 * media query and a `data-theme` scope, so the stamp set here wins over the OS
 * setting in either direction.
 */
export function ThemeToggle() {
  const [mode, setMode] = useState<Mode>("system");

  useEffect(() => {
    const saved = (localStorage.getItem(KEY) as Mode | null) ?? "system";
    setMode(saved);
    apply(saved);
  }, []);

  function apply(next: Mode) {
    const root = document.documentElement;
    if (next === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", next);
  }

  function cycle() {
    const order: Mode[] = ["system", "light", "dark"];
    const next = order[(order.indexOf(mode) + 1) % order.length];
    setMode(next);
    localStorage.setItem(KEY, next);
    apply(next);
  }

  return (
    <button
      type="button"
      onClick={cycle}
      className="press flex h-8 w-8 items-center justify-center rounded-full"
      style={{
        background: "var(--surface-1)",
        border: "1px solid var(--border-hairline)",
        color: "var(--text-secondary)",
      }}
      aria-label={`Theme: ${mode}. Tap to change.`}
      title={`Theme: ${mode}`}
    >
      {mode === "light" ? <IconSun /> : mode === "dark" ? <IconMoon /> : (
        <span className="relative flex h-4 w-4 items-center justify-center">
          <span
            aria-hidden
            className="absolute inset-0 rounded-full"
            style={{
              background: "linear-gradient(135deg, var(--text-secondary) 0 50%, transparent 50% 100%)",
              border: "1.5px solid var(--text-secondary)",
            }}
          />
        </span>
      )}
    </button>
  );
}
