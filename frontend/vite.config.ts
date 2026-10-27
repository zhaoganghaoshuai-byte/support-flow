import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          markdown: ["react-markdown", "remark-gfm"],
          "ui-vendor": ["@radix-ui/react-dialog", "@radix-ui/react-slot"],
        },
      },
    },
  },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8010" } },
});
