# rae — design system

The single reference for the design system used by `reverse-api-website`: the
raw tokens/assets **and** the opinionated layer on top of them. The tables in
**Reference** are mirrored from `website/src/app/global.css`; **Rules of use**
and everything below it is the personality, judgement, and *why*.

The personality in one line: **warm editorial-tech** — a cream paper canvas, a
high-character serif (Fraunces) used big and italic, monospace for technical
texture, a single hot-pink accent, and neo-brutalist hard-offset shadows.
Playful but precise.

---

## Reference

The source of truth for the exact palette, functional tokens, fonts + Fraunces
axis values, icon inventory, and shape/radius specs. Pulled from
`website/src/app/global.css`; always use the **token**, never the raw hex.

### Core Colors

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

### Functional Colors

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

### Backgrounds And Gradients

Utilities defined in `global.css`.

- `bg-color-mesh` light: `#fec5d4`, `#fff0e1`, `#ffd9c2`, `#fde0d3`, then `--color-cream`.
- `bg-color-mesh` dark: `#3a1822`, `#2a1f15`, `#2d1810`, `#281410`, then `--color-cream`.
- `bg-pastel-radial` light: `#c3f2d0`, `#b7ebff`, `#fee3cc`.
- `bg-pastel-radial` dark: `#1a2a22`, `#0d1b2e`, `#2a1810`.
- `bg-grid`, `bg-engineering`, `bg-dots`, `bg-scanlines`: patterns based on `color-mix(... var(--color-ink) ... transparent)`.

### Visible Hardcoded Colors

Some components still use inline colors, mostly lab variants and a few visual blocks.

- Home / current CTA: `#0d0a07`, `#14110e`, `#1f1f1f`, `#e50d75`, plus several `rgba(255,247,240,...)` and `rgba(0,0,0,...)` opacity values.
- Footer: `#0d0a07`, `rgba(229,13,117,0.28)`, `rgba(136,93,197,0.18)`, `rgba(255,247,240,...)`.
- App icon: `#e50d75`.
- Lab / non-canonical variants: `#0073e6`, `#080808`, `#0e0e0e`, `#1a1a1a`, `#2a2a2a`, `#6030b0`, `#885dc5`, `#a00060`, `#c00080`, `#c00a74`, `#c20000`, `#f0e8d4`, `#f5eedc`, `#f7f3ee`, `#faf8f4`, `#fff`, `#fffef9`, `#060504`, `#0a0806`, `#0d0907`, `#0e0c0a`, `#10100c`, `#131109`, `#1e1409`.

### Fonts

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

### Icons

#### Brand Icon

- Asterisk `*` set in italic `Fraunces`.
- Used in the header logo, hero/CTA decorations, marquee, and `website/src/app/icon.tsx`.
- Main color: `--color-fd-primary` (`#e50d75` in light mode, `#ff3d8b` in dark mode).
- The app icon loads only the `*` glyph from Fraunces.

#### Custom SVG Icons

- `GithubIcon`: inline SVG in `site-nav.tsx` and `page.tsx`.
- Color: `currentColor`, inherited from text classes such as `text-ink-soft` and `hover:text-ink`.

#### Lucide Icons

Library: `lucide-react`.

- `ArrowRightIcon`: CTA buttons, “Read the docs”, “Get started”, error pages.
- `SunIcon`: light theme switcher.
- `MoonIcon`: dark theme switcher.
- `RotateCcwIcon`: error page.
- `CopyIcon`: `InstallCommand` component.
- `CheckIcon`: `InstallCommand` component.
- `MenuIcon`: header variants in `components/lab`.

### Recurring Shapes And Patterns

- Buttons: `0.5rem` radius, pink offset shadow for primary buttons.
- Hero / landing cards: `1.5rem` radius, `ink/10` border, soft shadow.
- Tiles: `1.25rem` radius.
- Docs media: `0.75rem` radius.
- Header: glass background with `backdrop-blur-xl`, `backdrop-saturate-150`, and `color-mix(... --color-cream ... transparent)`.
- Decorations: Fraunces asterisks, scanlines, grids, dots, pastel mesh.

---

## Rules of use (the judgement the tokens don't encode)

**Palette**
- The page is always `cream`. Full-bleed sections alternate among the soft
  pastels (`orange` / `sky` / `mint` / `washed`) — never let two adjacent
  sections share a background.
- `fd-primary` (hot pink) is the **only** loud color and it's used *sparingly*:
  the asterisk motif, **one** accent word per heading (via `<em>`), node dots,
  the offset shadow on the primary button. If pink is showing up everywhere,
  pull it back — its power is its rarity.
- Borders are hairlines mixed from ink
  (`color-mix(in oklch, var(--color-ink) 12%, transparent)`), not solid black.
- Always use the **token** (`bg-cream`, `text-ink`, `text-fd-primary`), never the
  raw hex — so dark mode and re-theming just work.
- **The one exception:** an intentionally *physical* object — a dark terminal, the
  departure board (`#0d0a07`, `#1c1c1c`) — may use literal near-black values, so
  it reads as a real object sitting on any background. These are the
  "Visible Hardcoded Colors" listed in the Reference above; that list should stay
  *short* and deliberate, not grow.

**Type**
- Headings are **display serif (Fraunces) with one word in pink italic** via
  `<em>` — e.g. *"Works with the agent **you already use.**"* That single
  contrast is the house style.
- Mono (JetBrains) is for *technical texture*: eyebrows, tiny wide-tracked
  labels, status chips, code, numbers. Reach for it to make something feel
  "engineered."
- Use the expressive italic axis (`'SOFT' 100, 'WONK' 1`) for flourish; steadier
  axes for workhorse headings. (Exact axis values are in the Reference above.)

**The asterisk motif `*`**
- The recurring brand mark. A Fraunces italic `*` in pink. Float it in section
  corners at low opacity (`rotate-12` / `-rotate-12`), use it as the marquee
  divider, keep it in the logo. **Reach for it before inventing a new
  decoration** — it's the visual rhyme that ties unrelated sections together.

**Shape & shadow (neo-brutalist)**
- Prefer **hard offset shadows** (`3px 3px 0 0`, `4px 4px 0 0 var(--color-ink)`)
  over soft blur. The primary button *presses* on hover (shadow collapses to
  `1px 1px 0`, element nudges `translate(2px,2px)`).
- Bold elements get a `1.5px` ink border; quiet cards get a hairline ink-mix.
- Keep radii consistent (the set is in the Reference above), not random per element.

---

## Motion

- **Seamless marquee:** `marquee-track` + `@keyframes marquee-scroll` translate
  `-50%`. Bake spacing into each cell (`pr-*`), **never a flex `gap` on the
  animated track** — a gap breaks the loop's periodicity and it stutters. Repeat
  the set enough times that one half exceeds the viewport, or you'll see an empty
  gap before it repeats. `marquee-viewport:hover` pauses it.
- Transitions are short (`~180ms`) with `cubic-bezier(0, 0, 0.2, 1)`.
- **Every animation must degrade** under `@media (prefers-reduced-motion: reduce)`.
- Motion must *mean* something (a marquee = "ongoing", hover-pause = "inspect", a
  turning dial = "swappable"). Decorative motion gets cut.

**Lightning CSS gotcha:** a custom rule whose first declaration is `display: flex`
can be dropped when it collides with Tailwind's `flex` utility. Apply `flex` as a
utility class on the element and keep the rest of the rule in CSS.

---

## Iconography stance (the opinion behind the inventory)

The Icons reference above lists *what* icons exist. The *rules*:

- **No `lucide-react` on brand/marketing surfaces.** Its generic style (esp.
  `Bot`) reads as AI-slop. (lucide is fine for plain UI affordances — copy,
  theme toggle, arrows.) Brand/feature icons use **`@phosphor-icons/react`
  duotone**.
- **Real brand logos come from `simple-icons`** (monochrome single-path,
  rendered at `currentColor`). If a brand is missing (e.g. OpenCode), **draw a
  faithful custom mark from its favicon** — never substitute a generic glyph.
  See `website/src/components/brand-logos.tsx`.

---

## Worked exemplar: "Works with your agent"

Concept: an **airport split-flap departure board**. Each supported agent is a
row — its real logo, its name spelled in individual flap tiles (`bg-[#1c1c1c]`,
mono, inset bottom shadow), and a pink `SUPPORTED` status. The board is a dark
physical object (`#0d0a07` rounded card) sitting on a `mint` section; one small
display-serif heading with the pink-italic accent word sits underneath. See
`website/src/components/works-with-agents.tsx`, and the full 16-variant
exploration in [`examples.md`](./examples.md).
