import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  // Static export: all API calls use NEXT_PUBLIC_API_URL (empty = same origin).
  // Rewrites are not supported with output:"export" — the backend already handles
  // API routing via FastAPI routes and the catch-all frontend serve route.
  trailingSlash: true,
};

export default nextConfig;
