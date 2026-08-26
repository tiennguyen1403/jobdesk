/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    // usePolling keeps HMR reliable when running inside Docker on Windows
    watch: { usePolling: true },
  },
  test: {
    // jsdom gives component tests a DOM; globals enables Testing Library's
    // automatic cleanup between tests.
    environment: 'jsdom',
    globals: true,
  },
})
