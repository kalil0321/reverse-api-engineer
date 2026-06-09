# Case study — the rae `/lab` variant galleries

The `rae` site was designed by building an internal, gitignored `/lab` route
(`website/src/app/lab/page.tsx`) that held labelled galleries of variants for
each section, then promoting the standouts into real components. This is that
worked example: the concepts explored, what shipped, and why.

> The lab itself is **not committed** (it's in `website/.gitignore`). It's a
> sketchbook — its value is the breadth of exploration, not the code.

---

## Section 1 — feature marquee (under the hero)

A scrolling band of trust-signal tags. Four variants explored:

| Variant | Concept |
|---|---|
| M1 — Seamless mono ticker | dark band, mono tags, pink `*` dividers |
| M2 — Terminal status bar | a pinned `● live` badge; tags stream like a CLI log |
| M3 — Editorial serif | big Fraunces italic on cream, magazine masthead |
| M4 — Dual counter-scroll | two rows drifting opposite directions |

**Shipped: M1**, refined — `website/src/components/feature-marquee.tsx`. Tags:
*MIT licensed · Runs locally · No telemetry · Works with agents*, each with a
Phosphor **duotone** icon (no lucide), cream not pink.

**Lessons that became rules:**
- The original marquee stuttered because it put a flex `gap` *between* the two
  duplicated halves — that breaks the `-50%` loop's periodicity. Fix: bake
  spacing into each cell (`pr-*`), zero gap on the track.
- With only four short tags, one half was narrower than the viewport, so you saw
  an empty gap before it repeated. Fix: repeat the set N× per half until it
  exceeds any screen.
- Icons should be **one cream tone**, brighter than the text — not pink. A band
  that's pink everywhere loses the accent.

---

## Section 2 — "how it works" (four steps)

Started with the AI-slop default (four identical cards in a row) and deliberately
replaced it. ~14 variants explored, including:

S1 connected timeline · S3 editorial big-number · S4 interactive tabs (clean
code card, **no fake terminal chrome**) · S5 pipeline node graph · S6 vertical
rail with progress fill · S9 rotated index cards · S10 flow chips · S11 color-
block quarters · S12 staggered staircase · **S13 alternating spine** · S14
spec-sheet rows.

**Shipped: S13 — alternating spine.** Steps zig-zag left/right off a vertical
center line with pink node dots. See `HowItWorks` in
`website/src/app/(home)/page.tsx`. (The step numbers were later removed — the
dots carry the rhythm.)

**Lesson:** the four-identical-cards layout is the thing to *avoid*. Asymmetry
(the alternating spine) instantly reads as designed rather than generated.

---

## Section 3 — "works with your agent" (the standout)

The brief: convey that rae ships no model — it auto-detects and drives whichever
coding agent you already use (Claude Code, Cursor, GitHub Copilot, OpenCode).
**16 variants** explored, each a different physical-world metaphor:

| Variant | Metaphor |
|---|---|
| A1 — Orbit | logos orbit the rae `*` on dashed rings |
| A3 — Plug & socket | each agent plugs into a rae socket |
| A4 — Boarding-pass handoff | the brand's ticket motif: HAR → your agent → client.py |
| A6 — Swappable slot | interactive `rae + [ agent ]` picker |
| A8 — Sticker sheet | rotated die-cut logo stickers, offset shadows |
| A9 — Relay baton | capture → agent writes → rae reviews |
| A11 — Slot-machine reels | three reels of logos, "always lands on your agent" |
| A12 — Conveyor belt | HAR rides a belt through the rae machine |
| A13 — Constellation | agents as stars wired to a glowing rae core |
| A14 — Rotary dial | a selector that points at your agent |
| A15 — Passport stamps | inked "certified to run with" stamps |
| A16 — Isometric blocks | agent blocks feeding the taller rae block |
| A17 — Command palette | a ⌘K `rae use <agent>` picker |
| A18 — Filmstrip | agents as frames with sprocket holes |
| A19 — Circuit board | logos wired via PCB traces to the rae chip |
| **A20 — Split-flap board** | **airport departure board; each agent is a "departure"** |

**Shipped: A20 — split-flap departure board.**
`website/src/components/works-with-agents.tsx`. Each agent is a row: real logo
(simple-icons; a custom mark for OpenCode), its name in individual flap tiles
(`bg-[#1c1c1c]`, mono, inset bottom shadow), a pink `SUPPORTED` status. The dark
board sits as a physical object on a `mint` section, with one small display-serif
heading underneath.

**Lessons:**
- Real brand logos > generic icons. Pull from `simple-icons`; for a missing
  brand, draw a faithful custom mark from its favicon — don't substitute a
  generic glyph.
- The winner reused an existing motif (the boarding-pass/ticket already on the
  page), which is why A4 and A20 both felt "of the brand." Reuse beats inventing.
- Generating 16 and keeping 1 is the method, not waste. The split-flap idea
  wasn't in the first batch of 10 — it came from a second "give me 10 more,
  weirder" pass.

---

## The takeaway

None of the shipped sections is "a card grid." Each is a *named object* from the
physical world, executed inside one tight design system. That's the whole trick:
**concept first, breadth of exploration, ruthless selection, then polish.**
