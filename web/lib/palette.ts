/**
 * Chart palette, read from the CSS custom properties in globals.css so a
 * single definition drives both modes.
 *
 * Series colours are assigned by entity, never by rank: the map below is fixed,
 * so filtering the sport list never repaints the survivors.
 */
export const SERIES = {
  // Load chart. All three are in TSS units, so they share one axis.
  ctl: "var(--series-1)",
  atl: "var(--series-2)",
  tsb: "var(--series-3)",

  // Load by sport. Fixed assignment, in slot order.
  run: "var(--series-1)",
  bike: "var(--series-2)",
  swim: "var(--series-3)",
  strength: "var(--series-4)",

  // Single-series charts take slot 1.
  primary: "var(--series-1)",
} as const;

export const STATUS = {
  good: "var(--status-good)",
  warning: "var(--status-warning)",
  serious: "var(--status-serious)",
  critical: "var(--status-critical)",
  none: "var(--status-none)",
} as const;

export const CHROME = {
  grid: "var(--gridline)",
  axis: "var(--axis)",
  ink: "var(--text-primary)",
  inkSecondary: "var(--text-secondary)",
  muted: "var(--text-muted)",
  surface: "var(--surface-1)",
  bandFill: "var(--band-fill)",
  targetFill: "var(--target-fill)",
} as const;

/** Readiness band colour. Amber is used for readiness only, per the brief. */
export function readinessColor(band: string | null): string {
  if (band === "green") return STATUS.good;
  if (band === "amber") return STATUS.warning;
  if (band === "red") return STATUS.critical;
  return STATUS.none;
}

/** Habit state colour. Green hit, red missed, grey no data. Nothing else. */
export function habitColor(state: string): string {
  if (state === "hit") return STATUS.good;
  if (state === "missed") return STATUS.critical;
  return STATUS.none;
}

export const SPORT_ORDER = ["run", "bike", "swim", "strength"] as const;
export type Sport = (typeof SPORT_ORDER)[number];
