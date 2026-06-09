# Design guidelines — how to make work that doesn't look AI-generated

This folder captures the approach behind the `rae` marketing site and its `/lab`
design playground, so the same level of quality can be reproduced — by you, by
other people, or by another LLM.

- **README.md** (this file) — the methodology. The *why* and the *how*. Project-agnostic.
- **design-system.md** — the *opinionated layer* on `rae`'s system: the rules of
  use, the personality, the judgement. Project-specific.
- **PROMPT.md** — a paste-into-any-LLM prompt that generates this caliber of design.
- **examples.md** — a worked case study: the actual lab variants and why they work.

> **The canonical token/asset reference is [`../System_Design.md`](../System_Design.md)**
> — the exact palette, functional tokens, fonts + Fraunces axes, icon inventory,
> and shape/radius specs, mirrored from `website/src/app/global.css`. The
> `design-system.md` here deliberately does **not** repeat those tables; it adds
> the usage rules on top. Need a hex or a radius → read `System_Design.md`.

---

## The core problem: "AI slop"

Most LLM-generated UI converges on the same look: a centered hero, three
equal feature cards with a generic icon on top, a pricing table, lots of
`indigo-600`, evenly rounded corners, drop shadows everywhere, and zero point
of view. It's competent and completely forgettable.

The goal here is the opposite: **interfaces with a specific, deliberate
personality** — work that looks like a human with taste made a hundred small
decisions, because they did.

---

## The 10 principles

### 1. Commit to one strong idea per section
Every section should have a single concept you could name in three words.
"Split-flap departure board." "Alternating spine timeline." "Boarding-pass
handoff." If you can't name it, it's probably generic. The concept comes
*before* the layout — decide what the section *is* metaphorically, then build it.

> Bad: "a grid of the supported integrations."
> Good: "an airport split-flap board where each integration is a departure."

### 2. Steal structure from the physical world
The most memorable variants borrow from objects people already understand:
tickets, departure boards, slot machines, circuit boards, film strips, passport
stamps, rotary dials. These carry built-in meaning and instantly feel
intentional. When stuck, ask: *"What real-world object is this data like?"*

### 3. Have a typographic point of view
Generic design uses one sans-serif at three sizes. Distinctive design pairs a
**characterful display face** (a serif with real personality — high contrast, an
italic with flair, optical sizing) against a **functional body face** and a
**mono** for technical texture. The display face is the voice; use it big and
let it carry the brand.

### 4. Constrain the palette, then use it boldly
Pick a small palette (one ink, one paper, 3–4 soft accents, **one** loud accent)
and commit. The loud accent appears rarely and always means something. Avoid the
default framework blue. Warm neutrals (creams, off-whites) read more crafted than
pure `#fff`/`#000`. Full-bleed color blocks beat timid tinted cards.

### 5. Pick a signature motif and repeat it
One small recurring element ties everything together: an asterisk, a specific
arrow, a corner cut, a dotted seam. It should show up across sections like a
visual rhyme. Repetition of a deliberate detail reads as "designed"; randomness
reads as "generated."

### 6. Asymmetry and rhythm over uniform grids
Three identical cards in a row is the AI-slop default. Break it: alternate
left/right, stagger heights, give one element more weight (a hero cell, a
bento), offset things on purpose. Uniformity is safe and boring; controlled
imbalance creates rhythm and draws the eye.

### 7. Motion and interaction must mean something
Animation is not decoration. A marquee implies "ongoing." A pause-on-hover
implies "inspect this." A dial that turns implies "swappable." If an
interaction doesn't reinforce the concept, cut it. And it must respect
`prefers-reduced-motion`.

### 8. Sweat the micro-details
The gap between "fine" and "great" is in the 5%: a 1.5px border instead of 1px,
a hard offset shadow (`3px 3px 0`) instead of a soft blur, optical letter-spacing
on big type, a hairline divider, a mono label at `text-[10px]` with wide tracking,
edges that fade instead of hard-cut. These are individually invisible and
collectively everything.

### 9. Design tokens, never magic values
Pull every color, font, and radius from named variables — never hardcode a hex
that should be a token. This keeps a sprawling design coherent and makes
dark-mode / re-theming trivial. The one exception: an intentionally "physical"
object (a dark terminal, a departure board) may use literal values because it's
meant to read as a real-world thing on any background.

### 10. Generate many, keep few
Don't iterate one design to death. Produce **8–15 genuinely different takes** on
the same content in a throwaway gallery (a `/lab` page), look at them together,
and promote the 1–2 that sing. Breadth first, then ruthless selection. Most
will be mediocre; that's the point — you're hunting for the two that aren't.

---

## The process that produced this site

1. **Establish the system first.** Tokens, fonts, one motif, the palette —
   captured in `../System_Design.md` (the raw tokens) and `design-system.md`
   (the rules of use). Everything downstream pulls from it.
2. **Build a `/lab`.** An internal, unlinked, gitignored route that's a gallery
   of labelled variants. Each variant is wrapped in a frame with a one-line
   description of its concept. This is the sketchbook.
3. **Fan out.** For each section, write 5–15 variants with genuinely different
   *concepts* (not just recolors). Name each one.
4. **Review together, then cut.** Look at the whole gallery at once. Promote the
   standouts into real components; delete the rest.
5. **Polish the winner.** Port it out of the lab, swap magic values for tokens,
   make it theme-aware and reduced-motion-safe, verify it builds.

The lab is disposable scaffolding. Its value is the breadth of exploration, not
the code — keep it local (gitignored), never ship it.

---

## Anti-patterns — if you're doing these, stop

- Three (or four) identical feature cards, icon-on-top, in a tidy row.
- A generic icon library used as decoration (lucide's `Bot` etc. — instant "AI").
- Default framework blue / violet as the primary color.
- Everything the same border-radius, same soft drop-shadow.
- One sans-serif doing all the typographic work.
- Centered-hero → features → pricing → FAQ, in that exact order, with no surprises.
- Motion that's just "fade up on scroll" with no meaning.
- Filler copy ("Empower your workflow", "Seamlessly integrate", "Supercharge").
- Symmetry everywhere; no focal point; no point of view.

---

## How to use this with an LLM

Open `PROMPT.md`, paste it into a capable model, and append your project's
brief + (optionally) the contents of `design-system.md`. Ask it to produce a
`/lab`-style gallery of named variants for one section at a time, then you pick.
Quality comes from *breadth then selection* — instruct it to generate many,
not to perfect one.
