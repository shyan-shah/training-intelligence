"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";

import type { SeriesSpec } from "./Charts";
import { ChartSkeleton, Reveal, useMounted } from "./Motion";
import { BandMeter } from "./Gauge";
import { BottomNav, type Tab } from "./BottomNav";
import { ThemeToggle } from "./ThemeToggle";
import {
  Card, CheckRow, Delta, EmptyState, HabitLegend, ReadinessHero, Stat,
  StreakCalendar, SyncStamps,
} from "./Ui";
import {
  IconAlert, IconCheck, IconInsight, IconStreak, IconUpload,
} from "./Icons";
import { SERIES, STATUS, habitColor, readinessColor } from "@/lib/palette";
import {
  DASH, VERDICT_LABEL, km, num, pace, shortDate, signed,
} from "@/lib/format";
import {
  HABIT_LABELS, HABIT_WEEKLY_TARGET, baselineBand, bodyFatRows, clip,
  compositionRows, efficiencyRows, habitSeries, loadRows, recoveryRows,
  rollingMean, weeklyBySport, weightRows,
} from "@/lib/derive";
import type { TrainingData } from "@/lib/queries";

/* Recharts is ~100kB and only the chart tabs need it. Lazy-loading keeps it
   out of the Today bundle, which is the tab that has to open in under two
   seconds on a phone over 4G. Webpack folds these into one shared chunk, so
   the first chart tab pays for it once. */
const chartModule = () => import("./Charts");
const loading = () => <ChartSkeleton />;

const MultiLine = dynamic(() => chartModule().then((m) => m.MultiLine), { ssr: false, loading });
const BandedLine = dynamic(() => chartModule().then((m) => m.BandedLine), { ssr: false, loading });
const TrendWithPoints = dynamic(() => chartModule().then((m) => m.TrendWithPoints), { ssr: false, loading });
const StackedBars = dynamic(() => chartModule().then((m) => m.StackedBars), { ssr: false, loading });
const AcwrChart = dynamic(() => chartModule().then((m) => m.AcwrChart), { ssr: false, loading });
const StatusBars = dynamic(() => chartModule().then((m) => m.StatusBars), { ssr: false, loading });

const RANGES = [30, 90, 180, 3650] as const;
const RANGE_LABELS: Record<number, string> = { 30: "30d", 90: "90d", 180: "180d", 3650: "All" };
const RANGED_TABS: Tab[] = ["Body", "Load", "Recovery", "Performance"];

export default function TrainingTabs({ data }: { data: TrainingData }) {
  const [tab, setTab] = useState<Tab>("Today");
  const [range, setRange] = useState<number>(90);
  const [moreOpen, setMoreOpen] = useState(false);

  // Rendered only after mount: the server's date and the viewer's can differ.
  const mounted = useMounted();
  const today = mounted
    ? new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })
    : "";

  return (
    <>
      <div className="mx-auto w-full max-w-lg px-4 pb-32 pt-3">
        <header className="safe-top mb-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="eyebrow min-h-[13px]">{today}</div>
              <h1 className="mt-0.5 text-[26px] font-semibold leading-none tracking-tight">
                {tab}
              </h1>
            </div>
            <ThemeToggle />
          </div>

          <div className="mt-3">
            <SyncStamps sync={data.sync} />
          </div>

          {data.errors.length > 0 && (
            <p
              className="mt-2.5 flex items-start gap-1.5 rounded-lg px-2.5 py-2 text-[11px]"
              style={{ background: `${STATUS.critical}1f`, color: "var(--text-primary)" }}
            >
              <span style={{ color: STATUS.critical }}><IconAlert /></span>
              Some sources could not be read: {data.errors.join("; ")}
            </p>
          )}
        </header>

        {RANGED_TABS.includes(tab) && (
          <div
            className="mb-4 inline-flex rounded-xl p-0.5"
            style={{ background: "var(--surface-sunken)" }}
            role="group"
            aria-label="Date range"
          >
            {RANGES.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRange(r)}
                aria-pressed={range === r}
                className="press rounded-[10px] px-3 py-1.5 text-[11px] font-semibold"
                style={{
                  background: range === r ? "var(--surface-1)" : "transparent",
                  color: range === r ? "var(--text-primary)" : "var(--text-secondary)",
                  boxShadow: range === r ? "var(--shadow-sm)" : undefined,
                }}
              >
                {RANGE_LABELS[r]}
              </button>
            ))}
          </div>
        )}

        {/* Keyed so switching tabs replays the entrance animation. */}
        <div key={tab} className="animate-fade">
          {tab === "Today" && <TodayTab data={data} />}
          {tab === "Week" && <WeekTab data={data} />}
          {tab === "Streaks" && <StreaksTab data={data} />}
          {tab === "Body" && <BodyTab data={data} range={range} />}
          {tab === "Insights" && <InsightsTab data={data} />}
          {tab === "Load" && <LoadTab data={data} range={range} />}
          {tab === "Recovery" && <RecoveryTab data={data} range={range} />}
          {tab === "Performance" && <PerformanceTab data={data} range={range} />}
        </div>
      </div>

      <BottomNav tab={tab} setTab={setTab} moreOpen={moreOpen} setMoreOpen={setMoreOpen} />
    </>
  );
}

/* ================================ TODAY ================================ */
function TodayTab({ data }: { data: TrainingData }) {
  const today = data.readiness.at(-1);
  const wellness = data.daily.at(-1);
  const prev = data.daily.at(-2);
  const hrvValues = data.daily.map((d) => d.hrv_night);
  const band = baselineBand(hrvValues, 60);
  const latestLoad = data.loads.at(-1);

  const scorecardToday = data.scorecard.at(-1);
  const open = Object.entries(scorecardToday?.habits ?? {}).filter(([, s]) => s !== "hit");
  const hit = Object.entries(scorecardToday?.habits ?? {}).filter(([, s]) => s === "hit");
  const hasCheckin = data.checkins.some((c) => c.day === new Date().toISOString().slice(0, 10));

  const hrvColour =
    band && wellness?.hrv_night
      ? wellness.hrv_night < band.lo
        ? STATUS.critical
        : wellness.hrv_night > band.hi
          ? STATUS.warning
          : STATUS.good
      : undefined;

  const sleepHours = wellness?.sleep_total_min ? wellness.sleep_total_min / 60 : null;

  return (
    <div className="space-y-3.5">
      <Reveal>
        <ReadinessHero
          score={today?.score ?? null}
          band={today?.band ?? "unknown"}
          colour={readinessColor(today?.band ?? null)}
          drivers={today?.drivers ?? []}
          coldStart={today?.cold_start ?? false}
          garminReadiness={wellness?.readiness ?? null}
        />
      </Reveal>

      <div className="grid grid-cols-2 gap-3">
        <Reveal index={1}>
          <Stat
            label="HRV last night"
            value={num(wellness?.hrv_night ?? null, 0)}
            animate={wellness?.hrv_night ?? null}
            unit="ms"
            color={hrvColour}
            sub={band ? `Your band ${band.lo}\u2013${band.hi} ms` : "Baseline needs 14 nights"}
            spark={data.daily.slice(-21).map((d) => d.hrv_night)}
            sparkColor={hrvColour ?? SERIES.primary}
          />
        </Reveal>
        <Reveal index={2}>
          <Stat
            label="Sleep"
            value={sleepHours === null ? DASH : sleepHours.toFixed(1)}
            animate={sleepHours}
            dp={1}
            unit="h"
            sub={`Score ${num(wellness?.sleep_score ?? null, 0)}`}
            spark={data.daily.slice(-21).map((d) =>
              d.sleep_total_min === null ? null : d.sleep_total_min / 60)}
            sparkColor={SERIES.tsb}
          />
        </Reveal>
        <Reveal index={3}>
          <Stat
            label="Resting HR"
            value={num(wellness?.rhr ?? null, 0)}
            animate={wellness?.rhr ?? null}
            unit="bpm"
            spark={data.daily.slice(-21).map((d) => d.rhr)}
            sparkColor={SERIES.atl}
            delta={
              wellness?.rhr && prev?.rhr
                ? <Delta value={wellness.rhr - prev.rhr} unit=" bpm" dp={0} goodWhen="down" />
                : undefined
            }
          />
        </Reveal>
        <Reveal index={4}>
          <Stat
            label="Form"
            value={signed(latestLoad?.tsb ?? null, 1)}
            sub={`Fitness ${num(latestLoad?.ctl ?? null, 1)}`}
            spark={data.loads.slice(-21).map((l) => l.tsb)}
            sparkColor={SERIES.ctl}
          />
        </Reveal>
      </div>

      <Reveal index={5}>
        <Card
          title="Today's targets"
          subtitle={
            scorecardToday
              ? `${hit.length} of ${hit.length + open.length} hit`
              : "Written by tonight's compute"
          }
        >
          {!scorecardToday ? (
            <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
              No scorecard for today yet.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {Object.entries(scorecardToday.habits).map(([key, state]) => (
                <li
                  key={key}
                  className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] font-medium"
                  style={{
                    background: state === "hit" ? `${STATUS.good}1a` : "var(--surface-sunken)",
                    color: state === "hit" ? "var(--text-primary)" : "var(--text-secondary)",
                  }}
                >
                  <span
                    aria-hidden
                    className="inline-block h-2 w-2 rounded-[3px]"
                    style={{ background: habitColor(state) }}
                  />
                  {HABIT_LABELS[key] ?? key}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </Reveal>

      <Reveal index={6}>
        <Card title="Daily check-in" subtitle="20 seconds. Feeds 10% of readiness.">
          {hasCheckin ? (
            <p
              className="flex items-center gap-2 text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              <span
                className="flex h-5 w-5 items-center justify-center rounded-full"
                style={{ background: `${STATUS.good}22`, color: STATUS.good }}
              >
                <IconCheck size={11} />
              </span>
              Logged for today.
            </p>
          ) : (
            <CheckinForm />
          )}
        </Card>
      </Reveal>
    </div>
  );
}

const SLIDERS: [keyof CheckinState, string, number, number, string[]][] = [
  ["soreness", "Soreness", 1, 5, ["None", "Slight", "Some", "Sore", "Very sore"]],
  ["energy", "Energy", 1, 5, ["Flat", "Low", "Okay", "Good", "Flying"]],
  ["mood", "Mood", 1, 5, ["Bad", "Low", "Okay", "Good", "Great"]],
  ["niggle_pain", "Niggle pain", 0, 10, []],
];

type CheckinState = { soreness: number; energy: number; mood: number; niggle_pain: number };

function CheckinForm() {
  const [state, setState] = useState<CheckinState>({
    soreness: 3, energy: 3, mood: 3, niggle_pain: 0,
  });
  const [status, setStatus] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function submit() {
    setStatus("saving");
    setMessage(null);
    try {
      const res = await fetch("/api/checkin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
      setStatus("done");
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Could not save");
    }
  }

  if (status === "done") {
    return (
      <p className="flex items-center gap-2 text-xs" style={{ color: STATUS.good }}>
        <IconCheck size={13} /> Saved. It feeds tonight's readiness score.
      </p>
    );
  }

  return (
    <div className="space-y-3.5">
      {SLIDERS.map(([key, label, min, max, words]) => (
        <label key={key} className="block">
          <span className="flex items-baseline justify-between text-xs">
            <span style={{ color: "var(--text-secondary)" }}>{label}</span>
            <span className="tabular font-semibold">
              {words.length ? words[state[key] - min] : state[key]}
            </span>
          </span>
          <input
            type="range"
            min={min}
            max={max}
            value={state[key]}
            onChange={(e) => setState({ ...state, [key]: Number(e.target.value) })}
            className="mt-2 w-full"
          />
        </label>
      ))}
      <button
        type="button"
        onClick={submit}
        disabled={status === "saving"}
        className="press w-full rounded-xl px-3 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
        style={{ background: "var(--accent)", boxShadow: "0 6px 18px -8px var(--accent-glow)" }}
      >
        {status === "saving" ? "Saving" : "Log check-in"}
      </button>
      {message && (
        <p className="text-[11px]" style={{ color: STATUS.critical }}>{message}</p>
      )}
    </div>
  );
}

/* ================================= WEEK ================================= */
function WeekTab({ data }: { data: TrainingData }) {
  const report = data.weekly.at(0);
  const sportRows = weeklyBySport(data.loads, 8);
  const thisWeek = sportRows.at(-1);
  const topInsight = data.insights.at(0);

  const sportSeries: SeriesSpec[] = [
    { key: "run", label: "Run", color: SERIES.run, unit: "TSS", dp: 0 },
    { key: "bike", label: "Bike", color: SERIES.bike, unit: "TSS", dp: 0 },
    { key: "swim", label: "Swim", color: SERIES.swim, unit: "TSS", dp: 0 },
    { key: "strength", label: "Strength", color: SERIES.strength, unit: "TSS", dp: 0 },
  ];

  if (!report) {
    return (
      <EmptyState
        title="No weekly report yet"
        body="The weekly job runs Sunday at 18:31 Europe/London and writes the verdict with the numbers behind it."
      />
    );
  }

  const m = report.metrics as Record<string, any>;
  const colour =
    report.verdict === "push" ? STATUS.good
      : report.verdict === "back_off" ? STATUS.critical
        : STATUS.warning;

  return (
    <div className="space-y-3.5">
      <Reveal>
        <section
          className="panel relative overflow-hidden p-5"
          style={{
            background: `radial-gradient(120% 80% at 0% 0%, ${colour}1f, transparent 65%), var(--surface-1)`,
          }}
        >
          <div className="eyebrow">{report.iso_year} week {report.iso_week}</div>
          <div className="mt-1 flex items-center gap-2.5">
            <span
              aria-hidden
              className="inline-block h-3 w-3 rounded-full"
              style={{ background: colour, boxShadow: `0 0 12px ${colour}` }}
            />
            <h2
              className="text-[34px] font-semibold leading-none tracking-tight"
              style={{ color: colour }}
            >
              {VERDICT_LABEL[report.verdict]}
            </h2>
          </div>

          {report.narrative && (
            <p className="mt-2.5 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {report.narrative}
            </p>
          )}

          {/* The verdict never ships as a bare label: every rule shows its
              number and the threshold it was measured against. */}
          {Array.isArray(m.checks) && (
            <ul
              className="mt-4 border-t pt-2"
              style={{ borderColor: "var(--border-hairline)" }}
            >
              {m.checks.map((c: any, i: number) => (
                <CheckRow
                  key={i}
                  name={c.name}
                  passed={c.passed}
                  value={c.value === null ? DASH : String(c.value)}
                  threshold={c.threshold}
                />
              ))}
            </ul>
          )}

          {Array.isArray(m.unavailable) && m.unavailable.length > 0 && (
            <p className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
              Not assessed: {m.unavailable.join(", ")}
            </p>
          )}
        </section>
      </Reveal>

      {report.watch_flags.length > 0 && (
        <Reveal index={1}>
          <Card title="Watch this week">
            <ul className="space-y-2">
              {report.watch_flags.map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-xs leading-relaxed">
                  <span className="mt-0.5 shrink-0" style={{ color: STATUS.warning }}>
                    <IconAlert />
                  </span>
                  <span style={{ color: "var(--text-secondary)" }}>{f}</span>
                </li>
              ))}
            </ul>
          </Card>
        </Reveal>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Reveal index={2}>
          <Stat
            label="Load this week"
            value={num(
              thisWeek ? thisWeek.run + thisWeek.bike + thisWeek.swim + thisWeek.strength : null, 0)}
            unit="TSS"
            delta={
              m.week_tss_change_pct !== null && m.week_tss_change_pct !== undefined
                ? <Delta value={m.week_tss_change_pct} unit="%" dp={0} goodWhen="neither" />
                : undefined
            }
          />
        </Reveal>
        <Reveal index={3}>
          <Stat label="ACWR" value={num(m.acwr, 2)} sub="Band is 0.8 to 1.3" />
        </Reveal>
      </div>

      <Reveal index={4}>
        <StackedBars
          title="Load by sport"
          subtitle="Last 8 weeks, TSS"
          rows={sportRows}
          series={sportSeries}
          note="Walks and racquet sports are recorded but carry no TSS: there is no defensible load model for them here, so they are left out rather than estimated."
        />
      </Reveal>

      {topInsight && (
        <Reveal index={5}>
          <Card title="Top insight">
            <p className="text-sm leading-relaxed">{topInsight.headline}</p>
            {topInsight.detail && (
              <p className="mt-1.5 text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                {topInsight.detail}
              </p>
            )}
          </Card>
        </Reveal>
      )}
    </div>
  );
}

/* =============================== STREAKS =============================== */
function StreaksTab({ data }: { data: TrainingData }) {
  const series = habitSeries(data.scorecard);

  if (series.length === 0) {
    return (
      <EmptyState
        icon={<IconStreak size={28} />}
        title="No scorecard yet"
        body="Habit states are written nightly from the same rules the streak engine uses, so this fills in after the first compute run."
      />
    );
  }

  return (
    <div className="space-y-3.5">
      <HabitLegend />
      <div className="space-y-2.5">
        {series.map((h, i) => (
          <Reveal key={h.key} index={i}>
            <StreakCalendar
              label={HABIT_LABELS[h.key] ?? h.key}
              days={h.days}
              currentStreak={h.currentStreak}
              bestStreak={h.bestStreak}
              completion={h.completion}
              weeklyTarget={HABIT_WEEKLY_TARGET[h.key] ?? null}
              weekHits={h.weekHits}
            />
          </Reveal>
        ))}
      </div>
      <p className="text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
        A day with no data is grey and does not break a streak. Only a logged
        miss does.
      </p>
    </div>
  );
}

/* ================================= BODY ================================= */
function BodyTab({ data, range }: { data: TrainingData; range: number }) {
  const targets = data.settings?.targets ?? {};
  const bandKg: [number, number] = targets.weight_band_kg ?? [68, 70];

  const weights = weightRows(data.scans, []);
  const comp = compositionRows(data.scans);
  const bf = bodyFatRows(data.scans);

  const latest = data.scans.at(-1);
  const first = data.scans.at(0);
  const gainQuality =
    latest && first && latest !== first &&
    latest.weight_kg && first.weight_kg &&
    latest.skeletal_muscle_kg && first.skeletal_muscle_kg &&
    Math.abs(latest.weight_kg - first.weight_kg) >= 0.3
      ? (latest.skeletal_muscle_kg - first.skeletal_muscle_kg) /
        (latest.weight_kg - first.weight_kg)
      : null;

  return (
    <div className="space-y-3.5">
      <Reveal>
        <Card>
          <BandMeter
            value={latest?.weight_kg ?? null}
            min={Math.min(62, bandKg[0] - 4)}
            max={bandKg[1] + 3}
            bandLo={bandKg[0]}
            bandHi={bandKg[1]}
            colour={SERIES.primary}
            label={`Weight against the ${bandKg[0]} to ${bandKg[1]} kg target`}
            valueLabel={`${num(latest?.weight_kg ?? null, 1)} kg`}
          />
        </Card>
      </Reveal>

      <div className="grid grid-cols-2 gap-3">
        <Reveal index={1}>
          <Stat
            label="Body fat"
            value={num(latest?.body_fat_pct ?? null, 1)}
            animate={latest?.body_fat_pct ?? null}
            dp={1}
            unit="%"
          />
        </Reveal>
        <Reveal index={2}>
          <Stat
            label="Skeletal muscle"
            value={num(latest?.skeletal_muscle_kg ?? null, 1)}
            animate={latest?.skeletal_muscle_kg ?? null}
            dp={1}
            unit="kg"
          />
        </Reveal>
        <Reveal index={3}>
          <Stat
            label="Gain quality"
            value={gainQuality === null ? DASH : `${Math.round(gainQuality * 100)}%`}
            sub={
              gainQuality === null
                ? `${data.scans.length} scan${data.scans.length === 1 ? "" : "s"}, needs 2`
                : "of gain was muscle"
            }
          />
        </Reveal>
        <Reveal index={4}>
          <Stat
            label="Scans on record"
            value={String(data.scans.length)}
            sub={latest ? `Last ${shortDate(latest.scanned_at)}` : "None yet"}
          />
        </Reveal>
      </div>

      {data.scans.length < 3 && (
        <p
          className="flex items-start gap-1.5 rounded-xl px-3 py-2.5 text-[11px] leading-relaxed"
          style={{ background: "var(--surface-sunken)", color: "var(--text-secondary)" }}
        >
          <span className="mt-0.5 shrink-0" style={{ color: STATUS.warning }}>
            <IconAlert />
          </span>
          The composition trend uses a rolling 3-scan average. With{" "}
          {data.scans.length} scan{data.scans.length === 1 ? "" : "s"} on record
          the line is the raw reading, which swings with hydration and time of day.
        </p>
      )}

      <TrendWithPoints
        title="Weight"
        subtitle="Every weigh-in, smoothed trend, target band shaded"
        rows={clip(weights, range)}
        pointKey="weight"
        trendKey="trend"
        targetBand={{ lo: bandKg[0], hi: bandKg[1] }}
        unit="kg"
        dp={1}
        note="The trend is an exponential average with alpha 0.1, so one salty day does not move it."
      />

      {/* Masses and percentage are different units, so they get separate
          charts rather than a second y-axis. */}
      <MultiLine
        title="Composition"
        subtitle="Skeletal muscle and fat mass, 3-scan rolling average"
        rows={clip(comp, range)}
        series={[
          { key: "muscle_avg", label: "Skeletal muscle", color: SERIES.ctl, unit: "kg", dp: 1 },
          { key: "fat_avg", label: "Fat mass", color: SERIES.atl, unit: "kg", dp: 1 },
        ]}
      />

      <MultiLine
        title="Body fat percent"
        subtitle="3-scan rolling average"
        rows={clip(bf, range)}
        series={[{ key: "body_fat_avg", label: "Body fat", color: SERIES.tsb, unit: "%", dp: 1 }]}
        note="On its own chart: a percentage and a mass in kilograms cannot share one y-axis."
      />

      <Card title="Scans">
        {data.scans.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            No scans stored yet. Upload a PDF, or log one from any Claude chat.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {[...data.scans].reverse().map((s) => (
              <li
                key={s.scanned_at}
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs"
                style={{ background: "var(--surface-sunken)" }}
              >
                <span className="tabular shrink-0" style={{ color: "var(--text-secondary)" }}>
                  {shortDate(s.scanned_at)}
                </span>
                <span className="tabular truncate">
                  {num(s.weight_kg, 1)} kg · {num(s.body_fat_pct, 1)}% ·{" "}
                  {num(s.skeletal_muscle_kg, 1)} kg
                </span>
                {s.needs_review && (
                  <span
                    className="ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold"
                    style={{ background: `${STATUS.warning}2e` }}
                    title={s.review_reason ?? undefined}
                  >
                    review
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <ScanUpload />
      </Card>
    </div>
  );
}

function ScanUpload() {
  const [status, setStatus] = useState<"idle" | "up" | "done" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function upload(file: File) {
    setStatus("up");
    setMessage(null);
    const form = new FormData();
    form.set("file", file);
    try {
      const res = await fetch("/api/evolt", { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
      setStatus("done");
      setMessage(
        body.needs_review
          ? `Stored and flagged: ${body.review_reason}`
          : "Stored. It appears on the trend after tonight's compute.",
      );
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Upload failed");
    }
  }

  return (
    <div className="mt-3">
      <label
        className="press flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed px-3 py-3 text-xs font-medium"
        style={{ borderColor: "var(--border-hairline)", color: "var(--text-secondary)" }}
      >
        <IconUpload />
        {status === "up" ? "Uploading" : "Upload an Evolt PDF"}
        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
          }}
        />
      </label>
      {message && (
        <p
          className="mt-1.5 text-[11px] leading-relaxed"
          style={{ color: status === "error" ? STATUS.critical : "var(--text-secondary)" }}
        >
          {message}
        </p>
      )}
    </div>
  );
}

/* =============================== INSIGHTS =============================== */
function InsightsTab({ data }: { data: TrainingData }) {
  if (data.insights.length === 0) {
    return (
      <EmptyState
        icon={<IconInsight size={28} />}
        title="No insights yet"
        body="An insight only shows once there are 14 or more paired days and the effect clears day-to-day noise. Nothing has cleared both gates yet."
      />
    );
  }

  return (
    <div className="space-y-2.5">
      {data.insights.map((i, idx) => (
        <Reveal key={i.id} index={idx}>
          <Card>
            <p className="text-sm font-medium leading-relaxed">{i.headline}</p>
            {i.detail && (
              <p className="mt-1.5 text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                {i.detail}
              </p>
            )}
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              <Chip>n = {i.n}</Chip>
              {i.effect_size !== null && (
                <Chip>{signed(i.effect_size, 1)} {i.effect_unit}</Chip>
              )}
              {i.confidence !== null && <Chip>conf {i.confidence.toFixed(2)}</Chip>}
              {/* Correlation is labelled as correlation, every time. */}
              <Chip>{i.is_causal ? "causal" : "correlation, not cause"}</Chip>
            </div>
          </Card>
        </Reveal>
      ))}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="tabular rounded-md px-1.5 py-0.5 text-[10px] font-medium"
      style={{ background: "var(--surface-sunken)", color: "var(--text-muted)" }}
    >
      {children}
    </span>
  );
}

/* ================================= LOAD ================================= */
function LoadTab({ data, range }: { data: TrainingData; range: number }) {
  const rows = clip(loadRows(data.loads), range);
  const sportRows = weeklyBySport(data.loads, 12);
  const latest = data.loads.at(-1);
  const thresholds = data.settings?.thresholds ?? {};
  const acwrBand: [number, number] = thresholds.acwr_band ?? [0.8, 1.3];
  const rampMax = thresholds.ctl_ramp_max ?? 6;

  return (
    <div className="space-y-3.5">
      <div className="grid grid-cols-3 gap-2.5">
        <Reveal>
          <Stat
            label="Fitness"
            value={num(latest?.ctl ?? null, 1)}
            animate={latest?.ctl ?? null}
            dp={1}
            spark={data.loads.slice(-30).map((l) => l.ctl)}
            sparkColor={SERIES.ctl}
            sparkPosition="below"
          />
        </Reveal>
        <Reveal index={1}>
          <Stat
            label="Fatigue"
            value={num(latest?.atl ?? null, 1)}
            animate={latest?.atl ?? null}
            dp={1}
            spark={data.loads.slice(-30).map((l) => l.atl)}
            sparkColor={SERIES.atl}
            sparkPosition="below"
          />
        </Reveal>
        <Reveal index={2}>
          <Stat
            label="Form"
            value={signed(latest?.tsb ?? null, 1)}
            spark={data.loads.slice(-30).map((l) => l.tsb)}
            sparkColor={SERIES.tsb}
            sparkPosition="below"
          />
        </Reveal>
      </div>

      <MultiLine
        title="Fitness, fatigue and form"
        subtitle="All three in TSS units, so they share one axis"
        rows={rows}
        series={[
          { key: "ctl", label: "Fitness (CTL)", color: SERIES.ctl, dp: 1 },
          { key: "atl", label: "Fatigue (ATL)", color: SERIES.atl, dp: 1 },
          { key: "tsb", label: "Form (TSB)", color: SERIES.tsb, dp: 1 },
        ]}
        zeroLine
      />

      <AcwrChart
        rows={rows.filter((r) => r.acwr !== null)}
        band={acwrBand}
        note="Seven-day load over the 28-day weekly average. Blank until 28 days of history exist: a partial chronic window reads high and would fire a false back-off. The dashed line is the 1.5 back-off threshold."
      />

      <Card title="CTL ramp" subtitle={`Target is no more than about ${rampMax} points a week`}>
        <BandMeter
          value={latest?.ctl_ramp_7d ?? null}
          min={-6}
          max={12}
          bandLo={0}
          bandHi={rampMax}
          colour={
            latest?.ctl_ramp_7d && latest.ctl_ramp_7d > rampMax ? STATUS.warning : SERIES.ctl
          }
          label="Last 7 days"
          valueLabel={signed(latest?.ctl_ramp_7d ?? null, 1)}
        />
      </Card>

      <StackedBars
        title="Weekly load by sport"
        subtitle="TSS, last 12 weeks"
        rows={sportRows}
        series={[
          { key: "run", label: "Run", color: SERIES.run, dp: 0 },
          { key: "bike", label: "Bike", color: SERIES.bike, dp: 0 },
          { key: "swim", label: "Swim", color: SERIES.swim, dp: 0 },
          { key: "strength", label: "Strength", color: SERIES.strength, dp: 0 },
        ]}
      />

      <StatusBars
        title="Daily load"
        subtitle="TSS per day"
        rows={rows}
        valueKey="tss"
        label="TSS"
        colorFor={(r) => (r.tss > 120 ? STATUS.warning : SERIES.ctl)}
      />
    </div>
  );
}

/* =============================== RECOVERY =============================== */
function RecoveryTab({ data, range }: { data: TrainingData; range: number }) {
  const base = recoveryRows(data.daily);
  const withRolling = rollingMean(base, "hrv", 7, "hrv_roll");
  const rows = clip(withRolling, range);
  const band = baselineBand(data.daily.map((d) => d.hrv_night), 60);
  const latest = data.daily.at(-1);

  const sleepDebt = useMemo(() => {
    const target = (data.settings?.targets?.sleep_hours ?? 7.5) * 60;
    const last7 = data.daily.slice(-7)
      .map((d) => d.sleep_total_min)
      .filter((v): v is number => v !== null);
    if (last7.length === 0) return null;
    return +(last7.reduce((a, b) => a + (b - target), 0) / 60).toFixed(1);
  }, [data.daily, data.settings]);

  return (
    <div className="space-y-3.5">
      <div className="grid grid-cols-2 gap-3">
        <Reveal>
          <Stat
            label="HRV 7-day"
            value={num(rows.at(-1)?.hrv_roll ?? null, 0)}
            unit="ms"
            sub={band ? `Band ${band.lo}\u2013${band.hi} ms` : "Needs 14 nights"}
            spark={rows.slice(-30).map((r) => r.hrv_roll)}
            sparkColor={SERIES.primary}
          />
        </Reveal>
        <Reveal index={1}>
          <Stat
            label="Sleep debt, 7d"
            value={sleepDebt === null ? DASH : signed(sleepDebt, 1)}
            unit="h"
            color={sleepDebt !== null && sleepDebt < -3 ? STATUS.critical : undefined}
          />
        </Reveal>
        <Reveal index={2}>
          <Stat
            label="Resting HR"
            value={num(latest?.rhr ?? null, 0)}
            unit="bpm"
            spark={rows.slice(-30).map((r) => r.rhr)}
            sparkColor={SERIES.atl}
          />
        </Reveal>
        <Reveal index={3}>
          <Stat
            label="Stress average"
            value={num(latest?.stress_avg ?? null, 0)}
            spark={rows.slice(-30).map((r) => r.stress)}
            sparkColor={SERIES.strength}
          />
        </Reveal>
      </div>

      <BandedLine
        title="HRV against your own baseline"
        subtitle="Nightly reading, with the 60-day mean plus or minus one SD shaded"
        rows={rows}
        series={{ key: "hrv", label: "HRV", color: SERIES.primary, unit: "ms", dp: 0 }}
        band={band ? { lo: band.lo, hi: band.hi } : null}
        note="Below the band reads as strain. Above it is flagged too, since a sharp rise can be parasympathetic saturation rather than good news."
      />

      <MultiLine
        title="Resting heart rate"
        rows={rows}
        series={[{ key: "rhr", label: "Resting HR", color: SERIES.atl, unit: "bpm", dp: 0 }]}
      />

      <StatusBars
        title="Sleep score"
        subtitle="Green at or above the 75 target, red below"
        rows={rows}
        valueKey="sleep_score"
        label="Sleep score"
        colorFor={(r) =>
          r.sleep_score === null
            ? STATUS.none
            : r.sleep_score >= (data.settings?.targets?.sleep_score ?? 75)
              ? STATUS.good
              : STATUS.critical
        }
      />

      <MultiLine
        title="Sleep stages"
        subtitle="Minutes of deep and REM"
        rows={rows}
        series={[
          { key: "deep", label: "Deep", color: SERIES.ctl, unit: "min", dp: 0 },
          { key: "rem", label: "REM", color: SERIES.tsb, unit: "min", dp: 0 },
        ]}
      />

      <MultiLine
        title="Body battery"
        rows={rows}
        series={[
          { key: "body_battery_max", label: "Max", color: SERIES.ctl, dp: 0 },
          { key: "body_battery_min", label: "Min", color: SERIES.atl, dp: 0 },
        ]}
      />
    </div>
  );
}

/* ============================= PERFORMANCE ============================= */
function PerformanceTab({ data, range }: { data: TrainingData; range: number }) {
  const latest = data.daily.filter((d) => d.vo2max_run !== null).at(-1);
  const settings = data.settings;
  const runEf = clip(efficiencyRows(data.activities, "run"), range);
  const bikeEf = clip(efficiencyRows(data.activities, "bike"), range);

  const best = useMemo(
    () =>
      [...data.activities]
        .filter((a) => a.sport === "run" && a.distance_m && a.is_primary && a.is_valid)
        .sort((a, b) => (a.avg_pace ?? 1e9) - (b.avg_pace ?? 1e9))
        .slice(0, 5),
    [data.activities],
  );

  const css = settings?.css_swim
    ? `${Math.floor(settings.css_swim / 60)}:${String(Math.round(settings.css_swim % 60)).padStart(2, "0")}`
    : DASH;

  return (
    <div className="space-y-3.5">
      <div className="grid grid-cols-2 gap-3">
        <Reveal>
          <Stat
            label="FTP"
            value={num(settings?.ftp_w ?? null, 0)}
            animate={settings?.ftp_w ?? null}
            unit="W"
            sub="Measured"
          />
        </Reveal>
        <Reveal index={1}>
          <Stat
            label="Threshold pace"
            value={pace(settings?.threshold_pace ?? null)}
            sub={settings?.threshold_pace ? "Estimated from a 5k" : "Not set"}
          />
        </Reveal>
        <Reveal index={2}>
          <Stat
            label="CSS"
            value={css}
            unit={settings?.css_swim ? "/100m" : undefined}
            sub={settings?.css_swim ? undefined : "Needs a CSS test"}
          />
        </Reveal>
        <Reveal index={3}>
          <Stat
            label="VO2max"
            value={num(latest?.vo2max_run ?? null, 1)}
            sub={latest ? "Garmin login route" : "Login route not reporting"}
          />
        </Reveal>
      </div>

      <MultiLine
        title="Run efficiency"
        subtitle="Metres per beat. Rising at the same heart rate means aerobic fitness improving."
        rows={runEf}
        series={[{ key: "ef", label: "Metres per beat", color: SERIES.run, dp: 2 }]}
        note="Every run with a heart rate, not only steady ones, so an interval session reads low. Treat the trend rather than a single point."
      />

      {bikeEf.length > 0 && (
        <MultiLine
          title="Bike efficiency"
          rows={bikeEf}
          series={[{ key: "ef", label: "Metres per beat", color: SERIES.bike, dp: 2 }]}
        />
      )}

      <Card title="Fastest runs in range">
        {best.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            No runs with a pace in this range.
          </p>
        ) : (
          <ol className="space-y-1.5">
            {best.map((a, i) => (
              <li
                key={a.id}
                className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-xs"
                style={{ background: "var(--surface-sunken)" }}
              >
                <span
                  className="tabular flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold"
                  style={{ background: "var(--surface-1)", color: "var(--text-muted)" }}
                >
                  {i + 1}
                </span>
                <span className="tabular" style={{ color: "var(--text-secondary)" }}>
                  {shortDate(a.start_at)}
                </span>
                <span className="tabular">{km(a.distance_m)}</span>
                <span className="tabular ml-auto font-semibold">{pace(a.avg_pace)}</span>
              </li>
            ))}
          </ol>
        )}
        <p className="mt-2.5 text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
          Ranked on average pace. Peak speed is deliberately not used: GPS
          spikes make it unreliable.
        </p>
      </Card>

      {data.gear.filter((g) => g.gear_type === "shoe").length > 0 && (
        <Card title="Shoe mileage">
          <ul className="space-y-2.5">
            {data.gear
              .filter((g) => g.gear_type === "shoe")
              .sort((a, b) => b.distance_m - a.distance_m)
              .map((g) => {
                const frac = g.retire_at_m ? g.distance_m / g.retire_at_m : 0;
                const due = frac >= 1;
                const near = frac >= 0.85;
                const colour = due ? STATUS.critical : near ? STATUS.warning : SERIES.run;
                return (
                  <li key={g.source_id} className="text-xs">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">
                        {g.name ?? g.model_name ?? "Shoe"}
                      </span>
                      {(due || near) && (
                        <span
                          className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold"
                          style={{ background: `${colour}2e` }}
                        >
                          {due ? "replace" : "nearly due"}
                        </span>
                      )}
                      <span
                        className="tabular ml-auto shrink-0"
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {km(g.distance_m, 0)}
                        {g.retire_at_m ? ` / ${km(g.retire_at_m, 0)}` : ""}
                      </span>
                    </div>
                    <span
                      className="mt-1.5 block h-1.5 overflow-hidden rounded-full"
                      style={{ background: "var(--surface-sunken)" }}
                    >
                      <span
                        className="block h-full rounded-full"
                        style={{ width: `${Math.min(frac * 100, 100)}%`, background: colour }}
                      />
                    </span>
                  </li>
                );
              })}
          </ul>
        </Card>
      )}
    </div>
  );
}
