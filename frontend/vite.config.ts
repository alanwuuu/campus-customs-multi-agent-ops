import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API_TARGET = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000'

// The FastAPI backend owns the database and the agents; Vite only proxies /api to it.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { '/api': API_TARGET } },
})
