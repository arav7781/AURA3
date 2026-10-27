import type { NextConfig } from "next";

// The browser only talks to this origin: /api/* is forwarded to FastAPI, so the HttpOnly session
// cookie (a signed JWT) is first-party and no backend URL reaches client code.
const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8010").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async redirects() {
    return [
      { source: "/auth/investor", destination: "/register?role=investor", permanent: false },
      { source: "/auth/startup", destination: "/register?role=startup", permanent: false },
      // Pages from the wallet-based version
      { source: "/evaluations", destination: "/investor", permanent: false },
      { source: "/evaluation/:id", destination: "/investor", permanent: false },
      { source: "/proposal/:id", destination: "/investor", permanent: false },
      { source: "/finscope", destination: "/investor", permanent: false },
      { source: "/exit-window", destination: "/wallet", permanent: false },
      { source: "/portfolio", destination: "/wallet", permanent: false },
      { source: "/startup", destination: "/founder", permanent: false },
    ];
  },
  experimental: {
    proxyTimeout: 300_000, // evaluations and live event streams outlast the default 30 s
  },
};

export default nextConfig;
