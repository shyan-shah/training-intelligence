"use client";

import { useEffect } from "react";

import { IconClose, IconMore, TAB_ICONS } from "./Icons";

export const PRIMARY_TABS = ["Today", "Week", "Body", "Load"] as const;
export const MORE_TABS = ["Recovery", "Performance", "Streaks", "Insights"] as const;
export const ALL_TABS = [...PRIMARY_TABS, ...MORE_TABS] as const;
export type Tab = (typeof ALL_TABS)[number];

/**
 * Bottom navigation, because this is a phone-first app and the top of a
 * 6-inch screen is not reachable one-handed.
 *
 * Eight tabs will not fit across a phone, so the four most-used sit in the bar
 * and the rest live behind More. When a More tab is active the fifth slot
 * takes that tab's icon and name, so the bar always shows where you are.
 */
export function BottomNav({
  tab, setTab, moreOpen, setMoreOpen,
}: {
  tab: Tab;
  setTab: (t: Tab) => void;
  moreOpen: boolean;
  setMoreOpen: (v: boolean) => void;
}) {
  const inMore = (MORE_TABS as readonly string[]).includes(tab);
  const MoreIcon = inMore ? TAB_ICONS[tab] : IconMore;

  return (
    <>
      {moreOpen && <MoreSheet tab={tab} setTab={setTab} close={() => setMoreOpen(false)} />}

      <nav
        aria-label="Sections"
        className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t pt-1.5"
        style={{
          background: "var(--nav-bg)",
          backdropFilter: "var(--nav-blur)",
          WebkitBackdropFilter: "var(--nav-blur)",
          borderColor: "var(--border-hairline)",
        }}
      >
        <ul className="mx-auto flex max-w-lg items-stretch justify-around px-2">
          {PRIMARY_TABS.map((t) => (
            <NavItem
              key={t}
              label={t}
              Icon={TAB_ICONS[t]}
              active={tab === t}
              onClick={() => { setTab(t); setMoreOpen(false); }}
            />
          ))}
          <NavItem
            label={inMore ? tab : "More"}
            Icon={MoreIcon}
            active={inMore}
            onClick={() => setMoreOpen(!moreOpen)}
            expanded={moreOpen}
          />
        </ul>
      </nav>
    </>
  );
}

function NavItem({
  label, Icon, active, onClick, expanded,
}: {
  label: string;
  Icon: (p: { size?: number }) => JSX.Element;
  active: boolean;
  onClick: () => void;
  expanded?: boolean;
}) {
  return (
    <li className="flex-1">
      <button
        type="button"
        onClick={onClick}
        aria-current={active ? "page" : undefined}
        aria-expanded={expanded}
        className="press flex w-full flex-col items-center gap-0.5 rounded-xl px-1 py-1.5"
        style={{ color: active ? "var(--accent)" : "var(--text-muted)" }}
      >
        <span
          className="flex h-7 w-12 items-center justify-center rounded-full"
          style={{ background: active ? "var(--accent-wash)" : "transparent" }}
        >
          <Icon size={20} />
        </span>
        <span className="text-[10px] font-medium leading-none">{label}</span>
      </button>
    </li>
  );
}

function MoreSheet({
  tab, setTab, close,
}: {
  tab: Tab;
  setTab: (t: Tab) => void;
  close: () => void;
}) {
  // Escape closes, and the body does not scroll behind the sheet.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [close]);

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close"
        onClick={close}
        className="animate-fade absolute inset-0"
        style={{ background: "rgba(0,0,0,0.45)" }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="More sections"
        className="animate-rise safe-bottom absolute inset-x-0 bottom-0 rounded-t-3xl border-t p-4 pb-6"
        style={{
          background: "var(--surface-1)",
          borderColor: "var(--border-hairline)",
          boxShadow: "var(--shadow-lg)",
        }}
      >
        <div
          aria-hidden
          className="mx-auto mb-4 h-1 w-10 rounded-full"
          style={{ background: "var(--axis)" }}
        />
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">More</h2>
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            className="press rounded-full p-1.5"
            style={{ background: "var(--surface-sunken)", color: "var(--text-secondary)" }}
          >
            <IconClose />
          </button>
        </div>

        <ul className="grid grid-cols-2 gap-2">
          {MORE_TABS.map((t) => {
            const Icon = TAB_ICONS[t];
            const active = tab === t;
            return (
              <li key={t}>
                <button
                  type="button"
                  onClick={() => { setTab(t); close(); }}
                  className="press flex w-full items-center gap-2.5 rounded-xl p-3 text-left"
                  style={{
                    background: active ? "var(--accent-wash)" : "var(--surface-sunken)",
                    border: `1px solid ${active ? "var(--accent)" : "transparent"}`,
                    color: active ? "var(--accent)" : "var(--text-primary)",
                  }}
                >
                  <Icon size={20} />
                  <span className="text-sm font-medium">{t}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
