import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FastAPI backend (backend/api/app.py) runs on :8390; the app calls it under /api. Ports 5390 / 8390 keep clear of
// other local projects; `npm run dev` at the repo root (scripts/dev.sh) starts both and can move them.
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8390'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5390,
    strictPort: true, // a busy port fails instead of silently moving the app to another one
    proxy: {
      '/api': { target: backend, changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, '') },
    },
  },
})
