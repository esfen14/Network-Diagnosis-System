import { defineConfig } from 'vitest/config'

// Vitest picks this file over vite.config.ts. JSX is compiled by esbuild
// from tsconfig ("jsx": "react-jsx"), so the Vite plugins are not needed.
export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
