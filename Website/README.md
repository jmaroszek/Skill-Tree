# Skill Tree website

An Astro static site hosted on Cloudflare Workers Static Assets. The public page
currently says only `website under development`.

## Local development

Use Node.js 24.16.0, then run these commands from this folder:

```powershell
npm ci
npm run dev
```

`npm run build` generates `dist/`. `npm run preview` previews that build.
`npm run preview:cloudflare` also tests Cloudflare headers and redirects locally.
These commands do not publish anything.

## Publish

```powershell
npx wrangler login
npm run deploy:check
npm run deploy
```

`deploy:check` builds and validates the deployment without publishing.
`deploy` publishes immediately to the `skill-tree-website` Worker in Jonah's
Cloudflare account. The custom domains are `theskilltree.app` and
`www.theskilltree.app`; www redirects to the apex. Cloudflare manages DNS and TLS
for these Worker custom domains. There is no automatic Git deployment configured.

Wrangler authentication stays in the local user profile, outside this repository.
The account ID in `wrangler.jsonc` is an identifier, not a credential.

## Future development

Add pages under `src/pages/` and public files under `public/`. The current site
needs no database, cookies, or client JavaScript. A small Worker handler redirects
HTTP and www requests to the canonical HTTPS URL and serves static assets. Server endpoints
and storage can be added to this Worker when a feature requires them.

Before launching real content, revise the placeholder's `noindex` meta tag,
`public/robots.txt`, and `X-Robots-Tag` header together. Expand the restrictive
Content Security Policy only for resources the site actually uses.

References: [Static Assets](https://developers.cloudflare.com/workers/static-assets/)
and [Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).
