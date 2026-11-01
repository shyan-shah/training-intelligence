"use client";

import { useEffect, useRef, useState } from "react";

/**
 * False on the server and on the first client render, true afterwards.
 *
 * Anything derived from the current time has to wait for this. The server
 * renders in the container's timezone at the server's clock, the browser
 * renders in the viewer's, and React treats the difference as a hydration
 * mismatch. That is what "7 hours ago" and today's date were doing.
 */
export function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}

/** True when the viewer has asked for reduced motion. Every animated
 *  component here checks it and renders the final state immediately. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/**
 * Counts a number up on mount. Purely decorative, so it snaps straight to the
 * value under reduced motion and whenever the value is null.
 */
export function CountUp({
  value, dp = 0, duration = 700, prefix = "", suffix = "",
}: {
  value: number | null;
  dp?: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
}) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState<number | null>(reduced ? value : 0);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    if (value === null) { setShown(null); return; }
    if (reduced) { setShown(value); return; }

    const start = performance.now();
    const from = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(from + (value - from) * eased);
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, [value, duration, reduced]);

  if (shown === null) return <>{"—"}</>;
  return <>{prefix}{shown.toFixed(dp)}{suffix}</>;
}

/** Staggered entrance. `index` offsets the delay so a grid cascades. */
export function Reveal({
  children, index = 0, className = "",
}: {
  children: React.ReactNode;
  index?: number;
  className?: string;
}) {
  return (
    <div
      className={`animate-rise ${className}`}
      style={{ animationDelay: `${Math.min(index * 45, 360)}ms` }}
    >
      {children}
    </div>
  );
}

/** Shimmer placeholder, used while a lazily-loaded chart chunk arrives. */
export function Skeleton({ className = "", height = 16 }: { className?: string; height?: number }) {
  return <div className={`skeleton ${className}`} style={{ height }} />;
}

export function ChartSkeleton() {
  return (
    <div className="panel p-4">
      <Skeleton className="mb-3 w-1/3" height={13} />
      <Skeleton className="mb-4 w-1/2" height={10} />
      <Skeleton height={224} />
    </div>
  );
}
