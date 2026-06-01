# System Design

Quick reference for the design system used by `reverse-api-website`.

## Core Colors

These are the canonical color tokens defined in `website/src/app/global.css`.

| Token | Light | Dark | Usage |
| --- | --- | --- | --- |
| `--color-ink` | `#1f1f1f` | `#fff7f0` | Primary text, dark surfaces, strong borders |
| `--color-ink-soft` | `#1f1f1fcc` | `#fff7f0bb` | Secondary text |
| `--color-cream` | `#fff7f0` | `#14110e` | Main background |
| `--color-cream-soft` | `#fef8ee` | `#1c1814` | Slightly raised surfaces |
| `--color-orange` | `#ffe7d4` | `#3a1d0e` | Warm secondary section color |
| `--color-sky` | `#d6efff` | `#0d1b2e` | CTA section color |
| `--color-mint` | `#d5f1de` | `#0e2419` | Positive accent / completed state |
| `--color-washed` | `#f5f2ee` | `#1a1612` | Washed neutral background |

## Functional Colors

Tokens used by Fumadocs and shared components.

| Token | Light | Dark | Usage |
| --- | --- | --- | --- |
| `--color-fd-background` | `#fff7f0` | `#14110e` | App background |
| `--color-fd-foreground` | `#1f1f1f` | `#fff7f0` | App foreground text |
| `--color-fd-primary` | `#e50d75` | `#ff3d8b` | Pink accent, asterisk, links, CTA shadows |
| `--color-fd-primary-foreground` | `#fff7f0` | `#14110e` | Text on primary accent |
| `--color-fd-ring` | `#e50d75` | `#ff3d8b` | Focus ring |
| `--color-fd-accent` | `#ffe1eb` | `#2a1a22` | Soft accent |
| `--color-fd-accent-foreground` | `#1f1f1f` | `#fff7f0` | Text on accent |
| `--color-fd-card` | `#ffffff` | `#1c1814` | Cards |
| `--color-fd-card-foreground` | `#1f1f1f` | `#fff7f0` | Text on cards |
| `--color-fd-muted` | `#f5f2ee` | `#1a1612` | Muted backgrounds |
| `--color-fd-muted-foreground` | `#1f1f1f99` | `#fff7f0aa` | Muted text |
| `--color-fd-border` | `#1f1f1f1a` | `#fff7f014` | Subtle borders |

## Backgrounds And Gradients

Utilities defined in `global.css`.

- `bg-color-mesh` light: `#fec5d4`, `#fff0e1`, `#ffd9c2`, `#fde0d3`, then `--color-cream`.
- `bg-color-mesh` dark: `#3a1822`, `#2a1f15`, `#2d1810`, `#281410`, then `--color-cream`.
- `bg-pastel-radial` light: `#c3f2d0`, `#b7ebff`, `#fee3cc`.
- `bg-pastel-radial` dark: `#1a2a22`, `#0d1b2e`, `#2a1810`.
- `bg-grid`, `bg-engineering`, `bg-dots`, `bg-scanlines`: patterns based on `color-mix(... var(--color-ink) ... transparent)`.

## Visible Hardcoded Colors

Some components still use inline colors, mostly lab variants and a few visual blocks.

- Home / current CTA: `#0d0a07`, `#14110e`, `#1f1f1f`, `#e50d75`, plus several `rgba(255,247,240,...)` and `rgba(0,0,0,...)` opacity values.
- Footer: `#0d0a07`, `rgba(229,13,117,0.28)`, `rgba(136,93,197,0.18)`, `rgba(255,247,240,...)`.
- App icon: `#e50d75`.
- Lab / non-canonical variants: `#0073e6`, `#080808`, `#0e0e0e`, `#1a1a1a`, `#2a2a2a`, `#6030b0`, `#885dc5`, `#a00060`, `#c00080`, `#c00a74`, `#c20000`, `#f0e8d4`, `#f5eedc`, `#f7f3ee`, `#faf8f4`, `#fff`, `#fffef9`, `#060504`, `#0a0806`, `#0d0907`, `#0e0c0a`, `#10100c`, `#131109`, `#1e1409`.

## Fonts

Fonts are loaded in `website/src/app/layout.tsx` via `next/font/google`.

| Token | Font | Fallback | Usage |
| --- | --- | --- | --- |
| `--font-sans` | `Inter` | `ui-sans-serif`, `system-ui`, `sans-serif` | Body text, layout, buttons |
| `--font-display` | `Fraunces` | `ui-serif`, `Georgia`, `Times New Roman`, `serif` | `rae` logo, headlines, asterisk, editorial accents |
| `--font-mono` | `JetBrains Mono` | `SF Mono`, `Menlo`, `Monaco`, `Consolas`, `monospace` | Code, labels, eyebrows, numbers |

Frequently used Fraunces settings:

- `opsz`: `144`
- `SOFT`: often `30`, `40`, `50`, or `100`
- `WONK`: `0` or `1`
- Italic is used for headlines and the brand asterisk.

## Icons

### Brand Icon

- Asterisk `*` set in italic `Fraunces`.
- Used in the header logo, hero/CTA decorations, marquee, and `website/src/app/icon.tsx`.
- Main color: `--color-fd-primary` (`#e50d75` in light mode, `#ff3d8b` in dark mode).
- The app icon loads only the `*` glyph from Fraunces.

### Custom SVG Icons

- `GithubIcon`: inline SVG in `site-nav.tsx` and `page.tsx`.
- Color: `currentColor`, inherited from text classes such as `text-ink-soft` and `hover:text-ink`.

### Lucide Icons

Library: `lucide-react`.

- `ArrowRightIcon`: CTA buttons, “Read the docs”, “Get started”, error pages.
- `SunIcon`: light theme switcher.
- `MoonIcon`: dark theme switcher.
- `RotateCcwIcon`: error page.
- `CopyIcon`: `InstallCommand` component.
- `CheckIcon`: `InstallCommand` component.
- `MenuIcon`: header variants in `components/lab`.

## Recurring Shapes And Patterns

- Buttons: `0.5rem` radius, pink offset shadow for primary buttons.
- Hero / landing cards: `1.5rem` radius, `ink/10` border, soft shadow.
- Tiles: `1.25rem` radius.
- Docs media: `0.75rem` radius.
- Header: glass background with `backdrop-blur-xl`, `backdrop-saturate-150`, and `color-mix(... --color-cream ... transparent)`.
- Decorations: Fraunces asterisks, scanlines, grids, dots, pastel mesh.

