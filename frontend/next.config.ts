import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The container serves `next build`'s standalone server: a server.js and the modules
  // it was traced to import, without the rest of node_modules.
  output: "standalone",
};

export default nextConfig;
