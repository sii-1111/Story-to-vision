import type { NextConfig } from "next";

const apiBase = (process.env.STORY_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/stories/:path*",
        destination: `${apiBase}/api/stories/:path*`,
      },
      {
        source: "/api/projects/:path*",
        destination: `${apiBase}/api/projects/:path*`,
      },
      {
        source: "/api/videos/:path*",
        destination: `${apiBase}/api/videos/:path*`,
      },
      {
        source: "/health",
        destination: `${apiBase}/health`,
      },
    ];
  },
};

export default nextConfig;
