// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
const isDev = process.env.NODE_ENV !== "production";
// Browser test calls connect to LiveKit directly (signalling over WebSocket, plus its HTTP validation endpoint).
// Set at build time; the development default is the local LiveKit server from infra/compose.
const livekit = (process.env.XV_LIVEKIT_PUBLIC_URL ?? "ws://localhost:7880").replace(/\/$/, "");
const livekitHttp = livekit.replace(/^ws/, "http");
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "media-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self' ${livekit} ${livekitHttp}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Audio clips (speech-to-text test) and knowledge-base files (up to 5 MB, base64) go through server actions.
  experimental: { serverActions: { bodySizeLimit: "8mb" } },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=(self)" },
        ],
      },
    ];
  },
};
export default nextConfig;
