import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  // Read the shared monorepo .env only for this server-side proxy setting.
  // The browser always calls the same-origin /api URL.
  const env = loadEnv(
    mode,
    fileURLToPath(new URL('..', import.meta.url)),
    'VITE_',
  );
  const proxyTarget =
    process.env.VITE_API_PROXY_TARGET ||
    env.VITE_API_PROXY_TARGET ||
    'http://127.0.0.1:8000';

  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      clearMocks: true,
      restoreMocks: true,
    },
  };
});
