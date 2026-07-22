/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  // Local previews may be opened through 127.0.0.1 even though Next starts
  // with localhost. Without this, Next blocks the dev client and hydration,
  // leaving tabs, the theme toggle, and reveal effects inert.
  allowedDevOrigins: ['127.0.0.1'],
};

export default config;
