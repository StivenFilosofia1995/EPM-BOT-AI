import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Build autocontenido para la imagen Docker (ver frontend/Dockerfile).
  output: "standalone",
  // Evita que Next infiera un workspace root equivocado por lockfiles vecinos.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
