"use client";

/**
 * A 40px sparkline for a stat tile. Deliberately has no axis, no tooltip and
 * no legend: it shows shape, and the number beside it carries the value. The
 * full series with its hover layer lives on the matching tab.
 */
export function Sparkline({
  values, colour, width = 72, height = 28, fill = true,
}: {
  values: (number | null)[];
  colour: string;
  width?: number;
  height?: number;
  fill?: boolean;
}) {
  const points = values
    .map((v, i) => ({ v, i }))
    .filter((p): p is { v: number; i: number } => typeof p.v === "number");

  if (points.length < 2) {
    return <div style={{ width, height }} aria-hidden />;
  }

  const xs = points.map((p) => p.i);
  const ys = points.map((p) => p.v);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanY = maxY - minY || 1;
  const pad = 3;

  // Rounded for the same reason as the gauge: identical markup on server and
  // client, and 3dp is well under a pixel.
  const round = (n: number) => Math.round(n * 1000) / 1000;
  const sx = (i: number) => round(pad + ((i - minX) / (maxX - minX || 1)) * (width - pad * 2));
  const sy = (v: number) => round(height - pad - ((v - minY) / spanY) * (height - pad * 2));

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.i).toFixed(1)},${sy(p.v).toFixed(1)}`).join(" ");
  const area = `${path} L${sx(points.at(-1)!.i).toFixed(1)},${height} L${sx(points[0].i).toFixed(1)},${height} Z`;
  const last = points.at(-1)!;

  const gradientId = `spark-${colour.replace(/[^a-z0-9]/gi, "")}-${width}`;

  return (
    <svg width={width} height={height} aria-hidden className="shrink-0">
      {fill && (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colour} stopOpacity="0.28" />
              <stop offset="100%" stopColor={colour} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill={`url(#${gradientId})`} />
        </>
      )}
      <path
        d={path}
        fill="none"
        stroke={colour}
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={sx(last.i)} cy={sy(last.v)} r={2.4} fill={colour} />
    </svg>
  );
}
