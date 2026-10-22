/** @type {import('next').NextConfig} */
const rawBackend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
// Render passes a bare host ("pramaan-api.onrender.com"); add the scheme.
const backendUrl = rawBackend.startsWith("http") ? rawBackend.replace(/\/$/, "") : `https://${rawBackend}`;
if ((process.env.VERCEL || process.env.RENDER) && !process.env.BACKEND_URL) {
  throw new Error("Set BACKEND_URL to the backend address (e.g. https://pramaan-api.onrender.com) before building.");
}

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  poweredByHeader: false,
  images: { unoptimized: true },
  // OCR on a slow CPU can take a while; the default 30 s proxy timeout is too tight.
  experimental: { proxyTimeout: 120_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
