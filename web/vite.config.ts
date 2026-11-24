/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const backend = env.VITE_DEV_BACKEND || 'http://localhost:5000'

  // Demo mode: the whole app runs in the browser with a simulated station and sample
  // data (no backend, no database). On for `--mode demo`, and for Vercel *preview*
  // builds that have no backend configured, so every branch preview is clickable.
  const onVercel = env.VERCEL === '1'
  const demo = env.VITE_DEMO === '1' || (onVercel && env.VERCEL_ENV !== 'production' && !env.VITE_API_URL)

  // Production on Vercel: the app and the API live on different hosts, so without
  // VITE_API_URL the app would call itself for counts and uploads. Fail instead.
  if (onVercel && env.VERCEL_ENV === 'production' && !env.VITE_API_URL && !demo) {
    throw new Error('Set VITE_API_URL (e.g. https://aquacount-backend.onrender.com) in the Vercel project settings.')
  }

  return {
    define: { 'import.meta.env.VITE_DEMO': JSON.stringify(demo ? '1' : '') },
    plugins: [
      react(),
      VitePWA({
        registerType: 'prompt',
        injectRegister: false,
        includeAssets: ['favicon.svg', 'icons/apple-touch-icon.png'],
        manifest: {
          id: '/',
          name: 'AquaCount: Fingerling Counter',
          short_name: 'AquaCount',
          description: 'Count and grade catfish fingerlings on camera, then keep every batch on record.',
          lang: 'en',
          start_url: '/',
          scope: '/',
          display: 'standalone',
          background_color: '#0a101d',
          theme_color: '#0a101d',
          categories: ['productivity', 'utilities'],
          icons: [
            { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
            { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
            { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          ],
          shortcuts: [
            { name: 'Start a count', short_name: 'Count', url: '/count', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
            { name: 'Count history', short_name: 'History', url: '/history', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
          ],
        },
        workbox: {
          // App shell only. Counts, frames and sign-in always go to the network.
          globPatterns: ['**/*.{js,css,html,svg,png,webmanifest}', '**/*-latin-wght-normal-*.woff2'],
          navigateFallback: '/index.html',
          navigateFallbackDenylist: [/^\/api\//, /^\/socket\.io/, /^\/video_feed/],
          cleanupOutdatedCaches: true,
          maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
        },
      }),
    ],
    server: {
      port: 5173,
      proxy: {
        '/api': { target: backend, changeOrigin: false },
        '/socket.io': { target: backend, ws: true },
        '/video_feed': { target: backend },
      },
    },
    build: {
      target: 'es2020',
      rollupOptions: {
        output: {
          manualChunks: { react: ['react', 'react-dom', 'react-router-dom'], socket: ['socket.io-client'] },
        },
      },
    },
    test: { environment: 'node' },
  }
})
