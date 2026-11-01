import type { Metadata, Viewport } from "next";

import "./globals.css";
import { ThemeScript } from "./theme-script";

export const metadata: Metadata = {
  title: "Training",
  description: "Readiness, load, recovery and body composition in one place.",
  manifest: "/manifest.webmanifest",
  // Without an explicit apple-touch-icon, iOS uses a screenshot of the page
  // as the home screen icon.
  icons: {
    icon: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  // "black-translucent" lets the page draw under the status bar, which is why
  // the header carries a safe-area inset.
  appleWebApp: { capable: true, title: "Training", statusBarStyle: "black-translucent" },
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
        {/* Next emits the modern `mobile-web-app-capable`, which iOS only
            honours from 16.4. The legacy name is what makes an older iPhone
            open the installed app full screen instead of in a Safari chrome. */}
        <meta name="apple-mobile-web-app-capable" content="yes" />
      </head>
      <body>{children}</body>
    </html>
  );
}
