import type { Metadata, Viewport } from "next";

import "./globals.css";
import { ThemeScript } from "./theme-script";

export const metadata: Metadata = {
  title: "Training",
  description: "Readiness, load, recovery and body composition in one place.",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Training", statusBarStyle: "default" },
  // Personal health data: keep it out of search indexes entirely.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f9f9f7" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0d0d" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body>{children}</body>
    </html>
  );
}
