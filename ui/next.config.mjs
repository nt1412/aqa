/** @type {import('next').NextConfig} */
const BACKEND = process.env.AGENTQA_API_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    // Proxy API calls to the FastAPI backend so the browser hits same-origin /api.
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
