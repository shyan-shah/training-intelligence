/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Health data: never let a proxy or CDN hold a copy of a rendered page.
  async headers() {
    return [
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
