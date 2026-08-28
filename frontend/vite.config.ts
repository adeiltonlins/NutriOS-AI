import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/static/react-ui/',
  resolve: { alias: { '@': path.resolve(__dirname, '.') } },
  build: {
    outDir: path.resolve(__dirname, '../app/static/react-ui'),
    emptyOutDir: true,
    sourcemap: false,
  },
});
