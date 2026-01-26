import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";

// Development setup for Cloudflare
if (process.env.NODE_ENV === "development") {
  initOpenNextCloudflareForDev();
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
