import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://theskilltree.app',
  output: 'static',
  build: { inlineStylesheets: 'never' },
});
