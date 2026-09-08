import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default defineConfig([
  { ignores: ['dist/**', 'coverage/**', 'node_modules/**'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [reactHooks.configs.flat.recommended],
  },
  {
    files: ['src/**/*.tsx'],
    ignores: ['src/**/*.test.tsx'],
    extends: [reactRefresh.configs.vite],
  },
  {
    files: ['*.js'],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
]);
