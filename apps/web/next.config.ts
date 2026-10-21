import type { NextConfig } from "next";

// The browser talks to same-origin /api/*; Next forwards it to FastAPI so the
// session cookie stays first-party.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Let the dev server answer 127.0.0.1 as well as localhost (tests use it).
  allowedDevOrigins: ["127.0.0.1"],
  // Slate's pages are interactive client views that fetch on the client, so
  // Cache Components and partial prefetching are left off (see the v16
  // upgrade guide: enable them only when adopting that model).
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
