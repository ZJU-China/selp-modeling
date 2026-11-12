import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// Flow-centric frontend. Runs on 5174 and proxies /api to the same backend
// on 3001.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:3001", changeOrigin: true },
    },
  },
})
