/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output so the Docker runner stage can copy .next/standalone
  // and run `node server.js` without pulling node_modules at runtime.
  output: "standalone",
  // API proxy: forward /api/* to backend during development
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
