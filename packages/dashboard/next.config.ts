import type { NextConfig } from "next";

const PROMPTWALL_API_URL = process.env.PROMPTWALL_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${PROMPTWALL_API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
