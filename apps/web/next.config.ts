import path from "node:path";
import type { NextConfig } from "next";

// This folder is the whole app. Pinning it stops Next from treating a parent
// folder with its own lockfile (apps/desktop builds a copy of this one) as the root.
const ROOT = path.resolve(__dirname);

// /api/* is forwarded to FastAPI by proxy.ts.
const nextConfig: NextConfig = {
  // The Windows app bundles a self-contained server (NEXT_OUTPUT=standalone);
  // the website keeps the usual `next start`.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  outputFileTracingRoot: ROOT,
  experimental: {
    // proxy.ts buffers request bodies; uploads of course material go up to 50 MB.
    proxyClientMaxBodySize: "60mb",
  },
  // Let the dev server answer 127.0.0.1 as well as localhost (tests use it).
  allowedDevOrigins: ["127.0.0.1"],
  // Slate's pages are interactive client views that fetch on the client, so
  // Cache Components and partial prefetching are left off (see the v16
  // upgrade guide: enable them only when adopting that model).
  turbopack: {
    root: ROOT,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
