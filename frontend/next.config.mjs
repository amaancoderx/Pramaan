/** @type {import('next').NextConfig} */
const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
if (process.env.VERCEL && !process.env.BACKEND_URL) {
  throw new Error("Set BACKEND_URL in Vercel (e.g. https://<user>-pramaan-api.hf.space) before building.");
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
