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
2. If the Pages project does not exist yet, create it with
   `pnpm exec wrangler pages project create reverse-api-engineer --production-branch main`.
3. Optional: attach a custom domain via the Cloudflare dashboard.

### Automatic deployments (GitHub Actions)

The [`Deploy website` workflow](../.github/workflows/website.yml) builds with
Node.js 22 and pnpm 10.17.1, installs the committed lockfile, and uploads `out/`
to the existing `reverse-api-engineer` Pages project.

- Pushes that change `website/**` or the workflow itself trigger a deployment.
- Every branch other than `main` gets a preview. Its stable branch alias points
  to the latest deployment; the production site stays unchanged.
- Pushes to `main`, including merged pull requests, update production and its
  custom domains when those paths changed.
- Deployment and branch-preview links appear in the Actions run summary and
  GitHub's deployment status. No pull request is required for a branch preview.
- **Actions > Deploy website > Run workflow** can redeploy a selected branch
  manually, even without a website change, once the workflow exists on `main`.

One-time configuration:

1. In the repository's **Settings > Secrets and variables > Actions**, add these
   repository secrets:

   | Secret | Value |
   |--------|-------|
   | `CLOUDFLARE_API_TOKEN` | API token with **Account > Cloudflare Pages > Edit**, scoped to the account that owns the project. |
   | `CLOUDFLARE_ACCOUNT_ID` | That Cloudflare account's ID. |

2. Confirm the Pages project's **production branch is `main`**. Cloudflare uses
   this setting to distinguish production from preview deployments. For an
   existing Direct Upload project, follow the
   [production-branch configuration instructions](https://developers.cloudflare.com/pages/get-started/direct-upload/#production-branch-configuration).
3. If the Pages project also uses Cloudflare's Git integration, disable its
   automatic production and preview builds to avoid duplicate deployments;
   this workflow handles both through Wrangler.

The workflow runs on branch pushes in this repository. Fork pull requests do
not receive deployment credentials or publish previews in this account.
If you rename the Pages project, update both `wrangler.jsonc` and the workflow's
`--project-name` argument.

See Cloudflare's [CI deployment guide](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/)
and [preview deployment documentation](https://developers.cloudflare.com/pages/configuration/preview-deployments/).

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
