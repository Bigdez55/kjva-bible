import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
  resolve: {
    alias: {
      "@ds": path.resolve(__dirname, "../../design-system/src")
    }
  },
  build: {
    outDir: "dist/renderer"
  }
});
