/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output so the Docker runner stage can copy .next/standalone
  // and run `node server.js` without pulling node_modules at runtime.
  output: "standalone",
  // Same-origin proxy: forward /api/* + /sse/* to the backend container.
  // The browser bundle is built with NEXT_PUBLIC_API_BASE_URL="" /
  // NEXT_PUBLIC_SSE_URL="" so all client requests use relative paths and
  // ride this proxy — no CORS, no host-name surprises whether the user
  // browses from the host machine or a remote IP.
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/sse/:path*", destination: `${backend}/sse/:path*` },
    ];
  },
};

export default nextConfig;
