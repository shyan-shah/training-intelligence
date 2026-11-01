"use client";

import { useState, type ReactNode } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend,
  Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter,
  Tooltip, XAxis, YAxis,
} from "recharts";

import { CHROME } from "@/lib/palette";
import { DASH, shortDate } from "@/lib/format";

/* ------------------------------------------------------------------ *
 * Shared chart chrome.
 *
 * Rules applied throughout, from the data-viz spec:
 *   - 2px lines, >=8px active markers, recessive hairline grid.
 *   - A legend whenever there are two or more series; none for one, since the
 *     title names it. Up to four series are also direct-labelled, so identity
 *     is never carried by colour alone.
 *   - A crosshair plus tooltip on every line and area chart, and a per-mark
 *     tooltip on bars and cells.
 *   - One y-axis, always. Two measures on different scales get two charts.
 *   - A table view is available on every chart, which is also the relief for
 *     the light-mode aqua and yellow series sitting below 3:1 contrast.
 * ------------------------------------------------------------------ */

const AXIS_TICK = { fill: CHROME.muted, fontSize: 11 };
const MARGIN = { top: 16, right: 56, bottom: 4, left: 0 };

export type SeriesSpec = {
  key: string;
  label: string;
  color: string;
  unit?: string;
  dp?: number;
};

function TooltipBox({ active, payload, label, series }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-xl border px-3 py-2 text-xs"
      style={{
        background: CHROME.surface,
        borderColor: "var(--border-hairline)",
        color: CHROME.ink,
        boxShadow: "var(--shadow-lg)",
      }}
    >
      <div className="mb-1 font-medium">{label ? shortDate(String(label)) : ""}</div>
      {payload.map((p: any) => {
        const spec = series?.find((s: SeriesSpec) => s.key === p.dataKey);
        return (
          <div key={p.dataKey} className="flex items-center gap-2 tabular">
            <span
              aria-hidden
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: p.color ?? p.stroke }}
            />
            <span style={{ color: CHROME.inkSecondary }}>{spec?.label ?? p.name}</span>
            <span className="ml-auto font-medium">
              {p.value === null || p.value === undefined
                ? DASH
                : Number(p.value).toFixed(spec?.dp ?? 1)}
              {spec?.unit ? ` ${spec.unit}` : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Direct label pinned to the last point of a series. */
function endLabel(series: SeriesSpec, rows: any[]) {
  for (let i = rows.length - 1; i >= 0; i--) {
    const v = rows[i]?.[series.key];
    if (v !== null && v !== undefined) {
      return { value: Number(v).toFixed(series.dp ?? 0), color: series.color };
    }
  }
  return null;
}

function ChartFrame({
  title, subtitle, series, rows, children, note,
}: {
  title: string;
  subtitle?: string;
  series: SeriesSpec[];
  rows: any[];
  children: ReactNode;
  note?: string;
}) {
  const [showTable, setShowTable] = useState(false);

  return (
    <section className="panel p-4">
      <header className="mb-1 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
          {subtitle && (
            <p className="mt-0.5 text-xs leading-relaxed" style={{ color: CHROME.inkSecondary }}>
              {subtitle}
            </p>
          )}
        </div>
        {/* The table view is also the contrast relief for the light-mode
            aqua and yellow series, so it is on every chart, not optional. */}
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          className="press shrink-0 rounded-lg px-2 py-1 text-[11px] font-medium"
          style={{ background: "var(--surface-sunken)", color: CHROME.inkSecondary }}
          aria-pressed={showTable}
        >
          {showTable ? "Chart" : "Table"}
        </button>
      </header>

      {series.length > 1 && (
        <ul className="mb-2.5 mt-1.5 flex flex-wrap gap-x-3.5 gap-y-1 text-[11px]">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: s.color }}
              />
              <span style={{ color: CHROME.inkSecondary }}>{s.label}</span>
            </li>
          ))}
        </ul>
      )}

      {showTable ? (
        <DataTable series={series} rows={rows} />
      ) : rows.length === 0 ? (
        <EmptyChart />
      ) : (
        <div className="h-56 w-full sm:h-64">{children}</div>
      )}

      {note && (
        <p className="mt-2.5 text-[11px] leading-relaxed" style={{ color: CHROME.muted }}>
          {note}
        </p>
      )}
    </section>
  );
}

function EmptyChart() {
  return (
    <div
      className="flex h-56 items-center justify-center rounded-xl border border-dashed text-xs sm:h-64"
      style={{ borderColor: "var(--border-hairline)", color: CHROME.muted }}
    >
      No data in this range yet
    </div>
  );
}

function DataTable({ series, rows }: { series: SeriesSpec[]; rows: any[] }) {
  const recent = rows.slice(-30).reverse();
  return (
    <div className="max-h-64 overflow-auto">
      <table className="w-full text-left text-xs tabular">
        <thead
          className="sticky top-0"
          style={{ background: CHROME.surface, color: CHROME.inkSecondary }}
        >
          <tr>
            <th className="py-1 pr-2 font-medium">Date</th>
            {series.map((s) => (
              <th key={s.key} className="py-1 pr-2 text-right font-medium">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {recent.map((r, i) => (
            <tr key={i} style={{ borderTop: `1px solid ${CHROME.grid}` }}>
              <td className="py-1 pr-2" style={{ color: CHROME.inkSecondary }}>
                {r.day ? shortDate(r.day) : r.label ?? i}
              </td>
              {series.map((s) => (
                <td key={s.key} className="py-1 pr-2 text-right">
                  {r[s.key] === null || r[s.key] === undefined
                    ? DASH
                    : Number(r[s.key]).toFixed(s.dp ?? 1)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Multi-line chart. One axis, so every series must share a unit.
 * ------------------------------------------------------------------ */
export function MultiLine({
  title, subtitle, rows, series, note, zeroLine = false, bands = [],
}: {
  title: string;
  subtitle?: string;
  rows: any[];
  series: SeriesSpec[];
  note?: string;
  zeroLine?: boolean;
  bands?: { y1: number; y2: number; label?: string }[];
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} series={series} rows={rows} note={note}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={MARGIN}>
          <CartesianGrid stroke={CHROME.grid} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="day"
            tick={AXIS_TICK}
            tickFormatter={(v) => shortDate(String(v))}
            stroke={CHROME.axis}
            minTickGap={28}
          />
          <YAxis tick={AXIS_TICK} stroke={CHROME.axis} width={36} />
          {bands.map((b, i) => (
            <ReferenceArea
              key={i}
              y1={b.y1}
              y2={b.y2}
              fill={CHROME.bandFill}
              stroke="none"
              ifOverflow="extendDomain"
            />
          ))}
          {zeroLine && <ReferenceLine y={0} stroke={CHROME.axis} strokeWidth={1} />}
          <Tooltip
            content={<TooltipBox series={series} />}
            cursor={{ stroke: CHROME.axis, strokeWidth: 1 }}
          />
          {series.map((s) => {
            const end = endLabel(s, rows);
            return (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: CHROME.surface }}
                connectNulls
                label={
                  end && series.length <= 4
                    ? (props: any) =>
                        props.index === rows.length - 1 ? (
                          <text
                            x={props.x + 6}
                            y={props.y + 4}
                            fill={s.color}
                            fontSize={11}
                            fontWeight={600}
                          >
                            {end.value}
                          </text>
                        ) : (
                          <g />
                        )
                    : undefined
                }
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------------ *
 * Single series with a shaded baseline band. Used for HRV against its own
 * personal band, which is the whole point of the Recovery tab.
 * ------------------------------------------------------------------ */
export function BandedLine({
  title, subtitle, rows, series, band, note,
}: {
  title: string;
  subtitle?: string;
  rows: any[];
  series: SeriesSpec;
  band: { lo: number; hi: number } | null;
  note?: string;
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} series={[series]} rows={rows} note={note}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={MARGIN}>
          <CartesianGrid stroke={CHROME.grid} vertical={false} />
          <XAxis
            dataKey="day"
            tick={AXIS_TICK}
            tickFormatter={(v) => shortDate(String(v))}
            stroke={CHROME.axis}
            minTickGap={28}
          />
          <YAxis tick={AXIS_TICK} stroke={CHROME.axis} width={36} domain={["auto", "auto"]} />
          {band && (
            <ReferenceArea
              y1={band.lo}
              y2={band.hi}
              fill={CHROME.bandFill}
              stroke="none"
              ifOverflow="extendDomain"
            />
          )}
          <Tooltip
            content={<TooltipBox series={[series]} />}
            cursor={{ stroke: CHROME.axis, strokeWidth: 1 }}
          />
          <Line
            type="monotone"
            dataKey={series.key}
            stroke={series.color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: CHROME.surface }}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------------ *
 * Raw points plus a smoothed trend and a target band. The weight chart.
 * ------------------------------------------------------------------ */
export function TrendWithPoints({
  title, subtitle, rows, pointKey, trendKey, targetBand, note, unit, dp = 1,
}: {
  title: string;
  subtitle?: string;
  rows: any[];
  pointKey: string;
  trendKey: string;
  targetBand?: { lo: number; hi: number };
  note?: string;
  unit?: string;
  dp?: number;
}) {
  const series: SeriesSpec[] = [
    { key: pointKey, label: "Weigh-in", color: "var(--series-2)", unit, dp },
    { key: trendKey, label: "Trend", color: "var(--series-1)", unit, dp },
  ];
  return (
    <ChartFrame title={title} subtitle={subtitle} series={series} rows={rows} note={note}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={MARGIN}>
          <CartesianGrid stroke={CHROME.grid} vertical={false} />
          <XAxis
            dataKey="day"
            tick={AXIS_TICK}
            tickFormatter={(v) => shortDate(String(v))}
            stroke={CHROME.axis}
            minTickGap={28}
          />
          <YAxis tick={AXIS_TICK} stroke={CHROME.axis} width={40} domain={["auto", "auto"]} />
          {targetBand && (
            <ReferenceArea
              y1={targetBand.lo}
              y2={targetBand.hi}
              fill={CHROME.targetFill}
              stroke="none"
              ifOverflow="extendDomain"
            />
          )}
          <Tooltip
            content={<TooltipBox series={series} />}
            cursor={{ stroke: CHROME.axis, strokeWidth: 1 }}
          />
          <Scatter dataKey={pointKey} fill="var(--series-2)" shape="circle" r={4} />
          <Line
            type="monotone"
            dataKey={trendKey}
            stroke="var(--series-1)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: CHROME.surface }}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------------ *
 * Stacked bars. A 2px surface gap separates segments.
 * ------------------------------------------------------------------ */
export function StackedBars({
  title, subtitle, rows, series, note, xKey = "label",
}: {
  title: string;
  subtitle?: string;
  rows: any[];
  series: SeriesSpec[];
  note?: string;
  xKey?: string;
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} series={series} rows={rows} note={note}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={MARGIN} barCategoryGap="18%">
          <CartesianGrid stroke={CHROME.grid} vertical={false} />
          <XAxis dataKey={xKey} tick={AXIS_TICK} stroke={CHROME.axis} />
          <YAxis tick={AXIS_TICK} stroke={CHROME.axis} width={36} />
          <Tooltip
            content={<TooltipBox series={series} />}
            cursor={{ fill: "var(--band-fill)" }}
          />
          {series.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              stackId="a"
              fill={s.color}
              stroke={CHROME.surface}
              strokeWidth={2}
              radius={i === series.length - 1 ? [4, 4, 0, 0] : 0}
              className="series-fill"
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------------ *
 * ACWR with its band shaded. Single series, so no legend.
 * ------------------------------------------------------------------ */
export function AcwrChart({
  rows, band, note,
}: {
  rows: any[];
  band: [number, number];
  note?: string;
}) {
  const series: SeriesSpec = {
    key: "acwr",
    label: "ACWR",
    color: "var(--series-1)",
    dp: 2,
  };
  return (
    <ChartFrame
      title="Acute to chronic load ratio"
      subtitle={`Shaded band is ${band[0]} to ${band[1]}`}
      series={[series]}
      rows={rows}
      note={note}
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={MARGIN}>
          <CartesianGrid stroke={CHROME.grid} vertical={false} />
          <XAxis
            dataKey="day"
            tick={AXIS_TICK}
            tickFormatter={(v) => shortDate(String(v))}
            stroke={CHROME.axis}
            minTickGap={28}
          />
          <YAxis tick={AXIS_TICK} stroke={CHROME.axis} width={36} domain={[0, "auto"]} />
          <ReferenceArea
            y1={band[0]}
            y2={band[1]}
            fill={CHROME.targetFill}
            stroke="none"
            ifOverflow="extendDomain"
          />
          <ReferenceLine
            y={1.5}
            stroke="var(--status-critical)"
            strokeWidth={1}
            strokeDasharray="4 3"
          />
          <Tooltip
            content={<TooltipBox series={[series]} />}
            cursor={{ stroke: CHROME.axis, strokeWidth: 1 }}
          />
          <Area
            type="monotone"
            dataKey="acwr"
            stroke="var(--series-1)"
            strokeWidth={2}
            fill="var(--band-fill)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: CHROME.surface }}
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------------ *
 * Status bars, coloured by state rather than by series. Used for daily TSS
 * and sleep score, where each bar carries its own verdict.
 * ------------------------------------------------------------------ */
export function StatusBars({
  title, subtitle, rows, valueKey, colorFor, note, label, dp = 0,
}: {
  title: string;
  subtitle?: string;
  rows: any[];
  valueKey: string;
  colorFor: (row: any) => string;
  note?: string;
  label: string;
  dp?: number;
}) {
  const series: SeriesSpec[] = [
    { key: valueKey, label, color: "var(--series-1)", dp },
  ];
  return (
    <ChartFrame title={title} subtitle={subtitle} series={series} rows={rows} note={note}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={MARGIN}>
          <CartesianGrid stroke={CHROME.grid} vertical={false} />
          <XAxis
            dataKey="day"
            tick={AXIS_TICK}
            tickFormatter={(v) => shortDate(String(v))}
            stroke={CHROME.axis}
            minTickGap={28}
          />
          <YAxis tick={AXIS_TICK} stroke={CHROME.axis} width={36} />
          <Tooltip
            content={<TooltipBox series={series} />}
            cursor={{ fill: "var(--band-fill)" }}
          />
          <Bar dataKey={valueKey} radius={[4, 4, 0, 0]} className="series-fill">
            {rows.map((r, i) => (
              <Cell key={i} fill={colorFor(r)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
