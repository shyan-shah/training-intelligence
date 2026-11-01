"use client";

import { useEffect, useState } from "react";

import { CountUp, useReducedMotion } from "./Motion";

/**
 * The readiness arc. A 270 degree gauge, open at the bottom.
 *
 * The colour is a reserved status colour, so it never carries the meaning on
 * its own: the band is always named in text beside it, and the numeric score
 * is the primary read.
 */
export function ReadinessGauge({
  score, band, colour, size = 184, track = 14,
}: {
  score: number | null;
  band: string;
  colour: string;
  size?: number;
  track?: number;
}) {
  const reduced = useReducedMotion();
  const [swept, setSwept] = useState(reduced);

  useEffect(() => {
    if (reduced) { setSwept(true); return; }
    const id = requestAnimationFrame(() => setSwept(true));
    return () => cancelAnimationFrame(id);
  }, [reduced]);

  const r = (size - track) / 2 - 2;
  const centre = size / 2;
  const SWEEP = 0.75;                     // 270 of 360 degrees
  const frac = score === null ? 0 : Math.max(0, Math.min(score, 100)) / 100;

  /* Every number that reaches an SVG attribute is rounded.
     Math.cos and Math.sin are allowed to differ in the last bit between
     Node and V8, which is enough for React to call it a hydration mismatch
     (14.33436854000503 against 14.334368540005045). Rounding to 3dp is far
     below a pixel and makes the markup identical on both sides. */
  const round = (n: number) => Math.round(n * 1000) / 1000;

  const c = round(2 * Math.PI * r);
  const arc = round(c * SWEEP);
  const offset = round(arc * (1 - (swept ? frac : 0)));

  // A dot scale outside the ring, every 10 points. Drawn as dots rather than
  // radial ticks: tick lines at the two arc ends read as accidental spurs
  // sticking out of the gauge, dots do not.
  const scale = Array.from({ length: 11 }, (_, i) => {
    const rad = ((135 + (i / 10) * 270) * Math.PI) / 180;
    const ring = r + track / 2 + 6;
    return {
      cx: round(centre + Math.cos(rad) * ring),
      cy: round(centre + Math.sin(rad) * ring),
      major: i % 5 === 0,
      reached: frac * 100 >= i * 10,
    };
  });

  const label =
    band === "unknown" ? "Not enough data" : band[0].toUpperCase() + band.slice(1);

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        role="img"
        aria-label={
          score === null
            ? "Readiness not available"
            : `Readiness ${Math.round(score)} out of 100, ${label}`
        }
      >
        <defs>
          {/* A restrained bloom. At stdDeviation 6 the arc smeared into a
              blob; 3 reads as a lit instrument while the stroke stays crisp. */}
          <filter id="gauge-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComponentTransfer in="blur" result="dim">
              <feFuncA type="linear" slope="0.55" />
            </feComponentTransfer>
            <feMerge>
              <feMergeNode in="dim" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g transform={`rotate(135 ${centre} ${centre})`}>
          {/* Track */}
          <circle
            cx={centre}
            cy={centre}
            r={r}
            fill="none"
            stroke="var(--surface-sunken)"
            strokeWidth={track}
            strokeDasharray={`${arc} ${c}`}
            strokeLinecap="round"
          />
          {/* Value */}
          {score !== null && (
            <circle
              className="gauge-sweep"
              cx={centre}
              cy={centre}
              r={r}
              fill="none"
              stroke={colour}
              strokeWidth={track}
              strokeDasharray={`${arc} ${c}`}
              strokeDashoffset={offset}
              strokeLinecap="round"
              filter="url(#gauge-glow)"
              opacity={0.95}
            />
          )}
        </g>

        {scale.map((d, i) => (
          <circle
            key={i}
            cx={d.cx}
            cy={d.cy}
            r={d.major ? 1.8 : 1.1}
            fill={d.reached && score !== null ? colour : "var(--axis)"}
            opacity={d.reached && score !== null ? 0.75 : d.major ? 0.6 : 0.35}
          />
        ))}
      </svg>

      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <div
          className="text-[56px] font-semibold leading-none tracking-tight"
          style={{ color: "var(--text-primary)" }}
        >
          {score === null ? "—" : <CountUp value={score} dp={0} duration={900} />}
        </div>
        <div className="mt-1.5 flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: colour }}
          />
          <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
            {label}
          </span>
        </div>
        <div className="eyebrow mt-0.5">Readiness</div>
      </div>
    </div>
  );
}

/**
 * A small horizontal meter, used for a value against a target band. Shows the
 * band as a lighter region so "inside the band" is visible at a glance.
 */
export function BandMeter({
  value, min, max, bandLo, bandHi, colour, label, valueLabel,
}: {
  value: number | null;
  min: number;
  max: number;
  bandLo?: number;
  bandHi?: number;
  colour: string;
  label: string;
  valueLabel: string;
}) {
  const pos = (v: number) =>
    `${Math.round(((v - min) / (max - min)) * 100000) / 1000}%`;
  const clamped = value === null ? null : Math.max(min, Math.min(max, value));

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {label}
        </span>
        <span className="tabular text-xs font-semibold">{valueLabel}</span>
      </div>
      <div
        className="relative h-2 w-full overflow-hidden rounded-full"
        style={{ background: "var(--surface-sunken)" }}
      >
        {bandLo !== undefined && bandHi !== undefined && (
          <span
            className="absolute inset-y-0 rounded-full"
            style={{
              left: pos(bandLo),
              width: `${Math.round(((bandHi - bandLo) / (max - min)) * 100000) / 1000}%`,
              background: "var(--band-fill)",
            }}
          />
        )}
        {clamped !== null && (
          <span
            className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2"
            style={{
              left: pos(clamped),
              background: colour,
              borderColor: "var(--surface-1)",
              boxShadow: `0 0 8px ${colour}`,
            }}
          />
        )}
      </div>
      {/* Scale ends, so the dot's position means something. Without them the
          meter shows a dot on a bar and the viewer cannot read the range. */}
      <div
        className="mt-1 flex justify-between text-[10px] tabular"
        style={{ color: "var(--text-muted)" }}
      >
        <span>{min}</span>
        {bandLo !== undefined && bandHi !== undefined && (
          <span>
            target {bandLo}–{bandHi}
          </span>
        )}
        <span>{max}</span>
      </div>
    </div>
  );
}
