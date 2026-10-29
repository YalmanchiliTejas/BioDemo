/** Static export into dist/ so the existing nginx image (backend/deploy/cmo-ingestion) keeps serving the build. */
const nextConfig = {
  output: 'export',
  distDir: process.env.NEXT_DIST_DIR ?? 'dist',
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
