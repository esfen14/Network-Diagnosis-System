import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Test settings live in vitest.config.ts: Vitest 3 bundles its own Vite 7,
// so its `test` option does not type-check inside this Vite 8 config.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        // Override when port 5000 is taken (e.g. macOS AirPlay Receiver).
        target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})
