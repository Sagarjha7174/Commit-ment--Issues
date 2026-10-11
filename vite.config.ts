/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // In dev, /api (engine routes) and /llm (LLM routes) are proxied to the FastAPI app.
  const target = env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000'
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': { target, changeOrigin: true },
        '/llm': { target, changeOrigin: true },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes('node_modules/recharts') || id.includes('node_modules/d3-') || id.includes('node_modules/victory-vendor')) return 'charts'
            if (id.includes('node_modules/react') || id.includes('node_modules/scheduler')) return 'react'
            return undefined
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/tests/setup.ts'],
      css: false,
    },
  }
})
