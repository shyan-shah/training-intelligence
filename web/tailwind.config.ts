import type { Config } from "tailwindcss";

// Colours are declared as CSS custom properties in globals.css so the
// light/dark values swap in one place. Tailwind reads them by role here, which
// keeps raw hex out of component code.
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "var(--surface-1)",
        plane: "var(--plane)",
        ink: {
          DEFAULT: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
        },
        grid: "var(--gridline)",
        hairline: "var(--border-hairline)",
        good: "var(--status-good)",
        warning: "var(--status-warning)",
        critical: "var(--status-critical)",
        serious: "var(--status-serious)",
        s1: "var(--series-1)",
        s2: "var(--series-2)",
        s3: "var(--series-3)",
        s4: "var(--series-4)",
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
