/** Formatting helpers. Every one returns a dash for missing data rather than
 *  a zero, because a blank and a zero mean different things here. */

export const DASH = "—";

export function num(v: number | null | undefined, dp = 0): string {
  return v === null || v === undefined || Number.isNaN(v) ? DASH : v.toFixed(dp);
}

export function signed(v: number | null | undefined, dp = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return DASH;
  return `${v > 0 ? "+" : ""}${v.toFixed(dp)}`;
}

export function pct(v: number | null | undefined, dp = 0): string {
  return v === null || v === undefined ? DASH : `${(v * 100).toFixed(dp)}%`;
}

/** Seconds per km as m:ss. */
export function pace(secPerKm: number | null | undefined): string {
  if (!secPerKm || secPerKm <= 0) return DASH;
  const m = Math.floor(secPerKm / 60);
  const s = Math.round(secPerKm % 60);
  return `${m}:${String(s).padStart(2, "0")}/km`;
}

export function hours(seconds: number | null | undefined): string {
  if (!seconds) return DASH;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export function km(metres: number | null | undefined, dp = 1): string {
  return metres === null || metres === undefined ? DASH : `${(metres / 1000).toFixed(dp)} km`;
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function dayLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short",
  });
}

/** "3 hours ago" / "2 days ago", for the per-source sync stamp. */
export function since(iso: string | null): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.round(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

export function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  return Math.floor((new Date(iso).getTime() - Date.now()) / 86_400_000);
}

export const VERDICT_LABEL: Record<string, string> = {
  push: "Push",
  hold: "Hold",
  back_off: "Back off",
};
