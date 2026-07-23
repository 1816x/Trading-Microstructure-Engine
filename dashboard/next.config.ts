import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Same-origin proxy to the FastAPI backend: the backend serves no CORS
  // headers, so the browser only ever talks to this app's origin.
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
