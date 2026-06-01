# rae — design system (the opinionated layer)

> **Canonical token/asset reference: [`../System_Design.md`](../System_Design.md).**
> That file is the source of truth for the exact palette, functional tokens,
> fonts + Fraunces axis values, icon inventory, and shape/radius specs — pulled
> from `website/src/app/global.css`. **Don't duplicate it here.** When you need a
> hex, a font fallback, or a radius, read it there.
>
> This file adds what `System_Design.md` doesn't: the *personality*, the *rules
> of use*, and the *why*. It's the judgement layer on top of the raw tokens.

The personality in one line: **warm editorial-tech** — a cream paper canvas, a
high-character serif (Fraunces) used big and italic, monospace for technical
texture, a single hot-pink accent, and neo-brutalist hard-offset shadows.
Playful but precise.

---

## Rules of use (the judgement `System_Design.md` doesn't encode)

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
  it reads as a real object sitting on any background. `System_Design.md` lists
  these under "Visible Hardcoded Colors"; that list should stay *short* and
  deliberate, not grow.

**Type**
- Headings are **display serif (Fraunces) with one word in pink italic** via
  `<em>` — e.g. *"Works with the agent **you already use.**"* That single
  contrast is the house style.
- Mono (JetBrains) is for *technical texture*: eyebrows, tiny wide-tracked
  labels, status chips, code, numbers. Reach for it to make something feel
  "engineered."
- Use the expressive italic axis (`'SOFT' 100, 'WONK' 1`) for flourish; steadier
  axes for workhorse headings. (Exact values live in `System_Design.md`.)

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
- Keep radii consistent (the set is in `System_Design.md`), not random per element.

---

## Motion (not covered in System_Design.md)

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

`System_Design.md` lists *what* icons exist. The *rules*:

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
