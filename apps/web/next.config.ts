import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  agentRules: false,
  devIndicators: false,
};

export default nextConfig;

if (process.env.NODE_ENV !== "production") {
  import('@opennextjs/cloudflare').then(m => m.initOpenNextCloudflareForDev?.()).catch(() => {});
}
