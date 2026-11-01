/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The dev overlay badge sits exactly on top of the bottom navigation.
  devIndicators: false,
  // Health data: never let a proxy or CDN hold a copy of a rendered page.
  async headers() {
    return [
      {
        // A cached service worker never updates. The browser revalidates
        // sw.js on every navigation, so this must not be cacheable.
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
        ],
      },
      {
        source: "/training/:path*",
        headers: [
          { key: "Cache-Control", value: "private, no-store, max-age=0, must-revalidate" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};
export default nextConfig;
