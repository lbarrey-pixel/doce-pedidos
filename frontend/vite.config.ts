/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

// Site instalável (PWA): nome e ícones da Doce Ateliê. O service worker guarda o app; a API
// nunca é guardada (estoque e preço vêm sempre do servidor).
// Em desenvolvimento, /api vai para o backend local (uvicorn na porta 8000).
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icones/apple-touch-icon.png'],
      manifest: {
        name: 'Doce Ateliê',
        short_name: 'Doce Ateliê',
        description: 'Doces artesanais. Peça pelo celular e pague com Pix.',
        lang: 'pt-BR',
        start_url: '/',
        display: 'standalone',
        background_color: '#f5eedc',
        theme_color: '#953b1a',
        icons: [
          { src: '/icones/icone-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icones/icone-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icones/icone-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        globPatterns: ['**/*.{js,css,html,woff2,svg}', 'icones/*.png'],
      },
    }),
  ],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
  },
});
