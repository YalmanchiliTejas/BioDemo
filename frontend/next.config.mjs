/** Static export into dist/ so the existing nginx image (backend/deploy/cmo-ingestion) keeps serving the build. */
const nextConfig = {
  output: 'export',
  distDir: 'dist',
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
