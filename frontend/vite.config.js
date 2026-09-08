import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies API + media calls to the FastAPI backend on :8000,
// so the browser talks to a single origin and there are no CORS headaches.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/media': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
