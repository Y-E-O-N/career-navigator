import { setupDevPlatform } from '@cloudflare/next-on-pages/next-dev';

// Cloudflare Pages development setup
if (process.env.NODE_ENV === 'development') {
  await setupDevPlatform();
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloudflare Pages 호환 설정
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
