import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // Existing pages sync state from props/fetches inside effects. Surfaced as
      // warnings until each is refactored (see Implementation_Status.md).
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
  {
    // Context modules export a provider plus its hook and defaults by design.
    files: ['src/contexts/**/*.tsx'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
])
