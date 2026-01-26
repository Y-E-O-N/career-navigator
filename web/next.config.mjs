/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloudflare Pages 호환 설정
  images: {
    unoptimized: true,
  },
  // 실험적 기능
  experimental: {
    // Server Actions 활성화
    serverActions: {
      allowedOrigins: ['localhost:3000'],
    },
  },
};

export default nextConfig;
