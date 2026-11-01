/** Inline stroke icons, 24x24 grid, 1.75 stroke. Inline rather than an icon
 *  package so the bottom nav costs nothing to load. */
type P = { className?: string; size?: number; strokeWidth?: number };

function base({ size = 22, strokeWidth = 1.75, className }: P) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className,
    "aria-hidden": true,
  };
}

export const IconToday = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 12h3.5l2-5 3 10 2.5-7 1.6 4h5.4" />
  </svg>
);

export const IconWeek = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="5" width="18" height="16" rx="3" />
    <path d="M3 10h18M8 3v4M16 3v4" />
    <path d="M7.5 14.5h3M13.5 14.5h3M7.5 17.5h3" />
  </svg>
);

export const IconBody = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="5" r="2.4" />
    <path d="M6 10.5h12M9 10.5v4l-1.5 6M15 10.5v4l1.5 6" />
  </svg>
);

export const IconLoad = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 17.5c3-1 4.5-9 7-9s3.2 6 5 6 3.4-3.5 6-3.5" />
    <path d="M3 21h18" />
  </svg>
);

export const IconMore = (p: P) => (
  <svg {...base(p)}>
    <circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none" />
    <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
    <circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none" />
  </svg>
);

export const IconStreak = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="4" width="5" height="5" rx="1.2" />
    <rect x="10" y="4" width="5" height="5" rx="1.2" />
    <rect x="17" y="4" width="4" height="5" rx="1.2" />
    <rect x="3" y="11" width="5" height="5" rx="1.2" />
    <rect x="10" y="11" width="5" height="5" rx="1.2" />
    <rect x="3" y="18" width="5" height="3" rx="1.2" />
  </svg>
);

export const IconInsight = (p: P) => (
  <svg {...base(p)}>
    <path d="M9 18h6M10 21h4" />
    <path d="M12 3a6 6 0 0 0-3.6 10.8c.5.4.8 1 .9 1.6l.1.6h5.2l.1-.6c.1-.6.4-1.2.9-1.6A6 6 0 0 0 12 3Z" />
  </svg>
);

export const IconRecovery = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 13h3.5l1.8-4 2.4 8 2.2-6 1.4 2h6.7" />
    <path d="M20.5 7.5a3.6 3.6 0 0 0-5.2-1" />
  </svg>
);

export const IconPerformance = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
    <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
  </svg>
);

export const IconSun = (p: P) => (
  <svg {...base({ ...p, size: p.size ?? 18 })}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
  </svg>
);

export const IconMoon = (p: P) => (
  <svg {...base({ ...p, size: p.size ?? 18 })}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
  </svg>
);

export const IconUp = (p: P) => (
  <svg {...base({ ...p, size: p.size ?? 14, strokeWidth: 2.2 })}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </svg>
);

export const IconDown = (p: P) => (
  <svg {...base({ ...p, size: p.size ?? 14, strokeWidth: 2.2 })}>
    <path d="M12 5v14M19 12l-7 7-7-7" />
  </svg>
);

export const IconAlert = (p: P) => (
  <svg {...base({ ...p, size: p.size ?? 14, strokeWidth: 2 })}>
    <path d="M12 9v4M12 17h.01" />
    <path d="M10.3 3.9 2.4 17.1A2 2 0 0 0 4.1 20h15.8a2 2 0 0 0 1.7-2.9L13.7 3.9a2 2 0 0 0-3.4 0Z" />
  </svg>
);

export const IconCheck = (p: P) => (
  <svg {...base({ ...p, size: p.size ?? 14, strokeWidth: 2.4 })}>
    <path d="m4 12.5 5 5L20 6.5" />
  </svg>
);

export const IconClose = (p: P) => (
  <svg {...base({ ...p, size: p.size ?? 18, strokeWidth: 2 })}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);

export const IconUpload = (p: P) => (
  <svg {...base({ ...p, size: p.size ?? 18 })}>
    <path d="M12 16V4M7.5 8.5 12 4l4.5 4.5" />
    <path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" />
  </svg>
);

export const TAB_ICONS = {
  Today: IconToday,
  Week: IconWeek,
  Streaks: IconStreak,
  Body: IconBody,
  Insights: IconInsight,
  Load: IconLoad,
  Recovery: IconRecovery,
  Performance: IconPerformance,
} as const;
