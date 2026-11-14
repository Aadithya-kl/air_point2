import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    testTimeout: 10000,
    // One jsdom fork per test file is memory-hungry; with 15+ files the default
    // (one fork per logical CPU) crashed workers on the development machine.
    // Four workers keep the suite deterministic without changing any test.
    maxWorkers: 4,
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
