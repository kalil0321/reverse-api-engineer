# Reverse API Engineer — Marketing Site

Landing page + documentation for [`reverse-api-engineer`](https://github.com/kalil0321/reverse-api-engineer).

Built with [Next.js 16](https://nextjs.org) as a static export with custom MDX docs.
Deployed to [Cloudflare Pages](https://pages.cloudflare.com).

## Development

```bash
pnpm install
pnpm dev
```

Open http://localhost:3000.

## Project layout

| Path                       | What it is                                                              |
|----------------------------|-------------------------------------------------------------------------|
| `src/app/(home)/`          | Landing page (`/`).                                                     |
| `src/app/docs/`            | Documentation routes (`/docs/*`).                                       |
| `src/lib/shared.ts`        | App name, GitHub config, route names. **Edit here to rebrand.**         |
| `src/lib/docs.ts`          | MDX file loading, sidebar tree, prev/next nav, and TOC extraction.       |
| `src/components/docs/`     | Docs sidebar and MDX component mappings.                                |
| `content/docs/`            | All MDX content. Folders + `meta.json` define the sidebar tree.         |
| `next.config.mjs`          | Next.js config (`output: 'export'`, trailing slash, unoptimized images).|
| `wrangler.jsonc`           | Cloudflare Pages config.                                                |

## Adding docs

Drop an `.mdx` file in `content/docs/`. Frontmatter:

```mdx
---
title: My page
description: One-line description for SEO and search.
---

Content here.
```

To control sidebar order, edit the `meta.json` in the same folder.

## Build & deploy (Cloudflare Pages)

The site is a **Next.js static export** — every route is prerendered to HTML at
build time. Output goes to `./out/`. Cloudflare Pages serves it as static
assets. No Workers, no functions, no cold starts.

```bash
# build to ./out/
pnpm build

# preview via Wrangler Pages dev server
pnpm pages:preview

# deploy to Cloudflare Pages
pnpm pages:deploy
```

First-time setup:

1. `pnpm wrangler login`
2. Edit `name` in `wrangler.jsonc` if you want a different Pages project name.
3. Optional: attach a custom domain via the Cloudflare dashboard.

## Why static export?

The site has no server-side runtime needs:

- All docs pages are SSG (`generateStaticParams`).
- Docs MDX is read from `content/docs/` at build time.
- The icon route is generated at build time.

Static export keeps deploy trivial (`wrangler pages deploy out`), eliminates a
whole class of runtime config (no compatibility flags, no nodejs_compat shims),
and means the site is cached on Cloudflare's edge globally with zero per-request
cost.

## Links

- Project repo: <https://github.com/kalil0321/reverse-api-engineer>
- Cloudflare Pages: <https://pages.cloudflare.com>
