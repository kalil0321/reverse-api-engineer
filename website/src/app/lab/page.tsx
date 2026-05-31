'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Scales, HardDrives, EyeSlash, TerminalWindow } from '@phosphor-icons/react';
import { AGENTS, BrandIcon } from '@/components/brand-logos';

/* ───────────────────────────────────────────────────────────────────────────
   /lab — internal design exploration playground.

   Not linked from the site. A gallery of candidate designs for:
     1. the feature marquee (replacing the broken production one)
     2. the "four steps / how it works" section

   Each variant is wrapped in <Frame> so it reads as a labelled spec sheet.
   When we pick winners, we port them into the real components and delete the
   rejects from this file.
   ─────────────────────────────────────────────────────────────────────────── */


/* The shipping marquee set: four parallel "good citizen" trust signals,
   each with a leading Phosphor duotone icon (no robots). */
const FEATURES = [
  { Icon: Scales, label: 'MIT licensed' },
  { Icon: HardDrives, label: 'Runs locally' },
  { Icon: EyeSlash, label: 'No telemetry' },
  { Icon: TerminalWindow, label: 'Works with agents' },
];

const STEPS = [
  { num: '01', title: 'Browse', body: 'Open the CLI. Drive the browser yourself, or let the agent.' },
  { num: '02', title: 'Capture', body: 'HAR records every request, header, and response body.' },
  { num: '03', title: 'Generate', body: 'Your model reads the HAR and writes a typed client.' },
  { num: '04', title: 'Review', body: 'Audit the output, then commit it like any other code.' },
];

export default function LabPage() {
  return (
    <main className="min-h-screen bg-cream text-ink">
      {/* ── Lab header ── */}
      <header className="border-b border-ink/10">
        <div className="mx-auto max-w-7xl px-6 lg:px-10 py-10 flex items-end justify-between gap-6">
          <div>
            <p className="eyebrow text-ink-soft">Internal · not shipped</p>
            <h1 className="section-display mt-3">
              Design <em>lab</em>
            </h1>
            <p className="mt-4 max-w-xl text-sm md:text-base text-ink-soft leading-relaxed">
              Candidate designs for the marquee and the four-steps section. Hover
              a marquee to pause it. Pick the ones you like and I&apos;ll wire
              them into the real page.
            </p>
          </div>
          <Link href="/" className="btn-secondary shrink-0">
            ← Home
          </Link>
        </div>
      </header>

      {/* ── Four-steps explorations ── */}
      <Group n="02" title="Four steps" sub="How it works: Browse → Capture → Generate → Review.">
        <Frame label="S1 — Connected timeline" note="Numbered nodes on a single pink rail. Clear left-to-right progression.">
          <StepsTimeline />
        </Frame>

        <Frame label="S3 — Editorial big-number" note="Oversized serif numerals, vertical rhythm. Quiet and premium.">
          <StepsBigNumber />
        </Frame>

        <Frame label="S4 — Interactive tabs" note="Click a step to expand its detail + a clean code/output card (no terminal chrome).">
          <StepsTabs />
        </Frame>

        <Frame label="S5 — Pipeline node graph" note="Steps as connected nodes on a flow, like a data pipeline. Solid cards, no pink dots.">
          <StepsPipeline />
        </Frame>

        <Frame label="S6 — Vertical rail" note="Numbered nodes down a left rail with a live progress fill. Reads like a checklist.">
          <StepsVerticalRail />
        </Frame>

        <Frame label="S9 — Index cards" note="Rotated stamped cards with offset shadows. Playful, editorial, neo-brutalist.">
          <StepsIndexCards />
        </Frame>

        <Frame label="S10 — Flow chips" note="One row of big rounded chips connected by arrows. Compact process flow, light bg.">
          <StepsFlowChips />
        </Frame>

        <Frame label="S11 — Color-block quarters" note="Four full-bleed panels in the brand pastels with big number watermarks. Bold & editorial.">
          <StepsColorBlocks />
        </Frame>

        <Frame label="S12 — Staggered staircase" note="Cards descend step-by-step in a 4-col grid. Visually literal 'steps'.">
          <StepsStaircase />
        </Frame>

        <Frame label="S13 — Alternating spine" note="Center timeline; steps alternate left/right off a vertical spine. Classic & elegant.">
          <StepsSpine />
        </Frame>

        <Frame label="S14 — Spec-sheet rows" note="Minimal hairline-separated rows, big mono numbers. Documentation/technical aesthetic.">
          <StepsSpecSheet />
        </Frame>
      </Group>

      {/* ── Works-with-your-agent explorations ── */}
      <Group n="03" title="Works with your agent" sub="rae ships no model — it drives the coding agent you already use.">
        <Frame label="A1 — Orbit" note="Agent logos orbit the rae asterisk on dashed rings. 'Everything revolves around your agent.'">
          <AgentsOrbit />
        </Frame>

        <Frame label="A3 — Plug & socket" note="Each agent is a plug that seats into a rae socket. Literal 'plug in your agent'.">
          <AgentsSockets />
        </Frame>

        <Frame label="A4 — Boarding-pass handoff" note="Reuses the ticket motif: HAR → [your agent] → typed client, agent in the stub.">
          <AgentsHandoff />
        </Frame>

        <Frame label="A6 — Swappable slot" note="One big 'rae + [ slot ]' line; the slot cycles through agents like a picker.">
          <AgentsSlot />
        </Frame>

        <Frame label="A8 — Sticker sheet" note="Die-cut logo stickers, slightly rotated with offset shadows. Playful, tactile.">
          <AgentsStickers />
        </Frame>

        <Frame label="A9 — Relay baton" note="Capture passes the baton to your agent, which hands back the client. Sequential story.">
          <AgentsRelay />
        </Frame>

        <Frame label="A11 — Slot-machine reels" note="Three reels of agent logos; rae always lands on yours. Arcade energy.">
          <AgentsReels />
        </Frame>

        <Frame label="A12 — Conveyor belt" note="HAR rides a belt through a rae machine; agent logos stamp it into a client.">
          <AgentsConveyor />
        </Frame>

        <Frame label="A13 — Constellation" note="Agents as stars joined by faint lines to the rae core. Cosmic, premium.">
          <AgentsConstellation />
        </Frame>

        <Frame label="A14 — Rotary selector" note="A dial that points to whichever agent you use; tick marks all around.">
          <AgentsDial />
        </Frame>

        <Frame label="A15 — Passport stamps" note="Inked rotated stamps over a document — 'certified to run with'. Tactile.">
          <AgentsStamps />
        </Frame>

        <Frame label="A16 — Isometric blocks" note="Agents as 3D-ish stacked blocks feeding into the rae block. Playful depth.">
          <AgentsBlocks />
        </Frame>

        <Frame label="A17 — Command palette" note="A ⌘K picker: 'rae use <agent>' with each agent as a result row.">
          <AgentsPalette />
        </Frame>

        <Frame label="A18 — Filmstrip" note="Agents as frames in a film strip with sprocket holes. Sequential, editorial.">
          <AgentsFilmstrip />
        </Frame>

        <Frame label="A19 — Circuit board" note="Logos wired with PCB traces + solder pads into the rae chip. Hardware vibe.">
          <AgentsCircuit />
        </Frame>

        <Frame label="A20 — Split flap board" note="Airport-style flap display flips through agent names. Retro-mechanical.">
          <AgentsSplitFlap />
        </Frame>
      </Group>

      <div className="h-24" />
    </main>
  );
}

/* ───────────────────────── Gallery scaffolding ─────────────────────────── */

function Group({
  n,
  title,
  sub,
  children,
}: {
  n: string;
  title: string;
  sub: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-auto max-w-7xl px-6 lg:px-10 py-14">
      <div className="flex items-baseline gap-4 mb-8">
        <span className="font-mono text-xs text-fd-primary">{n}</span>
        <h2 className="font-display text-3xl tracking-tight">{title}</h2>
        <span className="text-sm text-ink-soft">{sub}</span>
      </div>
      <div className="grid grid-cols-1 gap-10">{children}</div>
    </section>
  );
}

function Frame({
  label,
  note,
  children,
}: {
  label: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2.5">
        <span className="lab-chip text-ink">{label}</span>
        <span className="text-xs text-ink-soft max-w-md text-right">{note}</span>
      </div>
      <div className="lab-frame">{children}</div>
    </div>
  );
}

/* ════════════════════════════ FOUR STEPS ══════════════════════════════════ */

/* S1 — Connected timeline --------------------------------------------------- */
function StepsTimeline() {
  return (
    <div className="bg-orange px-6 lg:px-10 py-16">
      <div className="relative grid grid-cols-1 md:grid-cols-4 gap-10 md:gap-6">
        {/* rail */}
        <div className="hidden md:block absolute left-0 right-0 top-5 h-px bg-ink/15" />
        {STEPS.map((s) => (
          <div key={s.num} className="relative">
            <div className="relative z-10 flex size-10 items-center justify-center rounded-full bg-ink text-cream font-mono text-sm shadow-[3px_3px_0_0_var(--color-fd-primary)]">
              {s.num}
            </div>
            <h3 className="mt-5 font-display text-2xl tracking-tight">{s.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-ink-soft max-w-[24ch]">{s.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* S3 — Editorial big-number ------------------------------------------------- */
function StepsBigNumber() {
  return (
    <div className="bg-cream px-6 lg:px-10 py-16">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-16 gap-y-12 max-w-4xl">
        {STEPS.map((s) => (
          <div key={s.num} className="flex gap-6">
            <span
              className="font-display italic leading-none text-fd-primary/30 text-6xl select-none"
              style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
            >
              {s.num}
            </span>
            <div className="pt-1">
              <h3 className="font-display text-2xl tracking-tight">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">{s.body}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* S4 — Interactive tabs -----------------------------------------------------
   Click a step on the left; the right side shows a clean code/output card.
   No terminal chrome (no traffic-light dots): the preview is an editorial
   card with a labelled caption header and a soft inset code body. */
function StepsTabs() {
  const [active, setActive] = useState(0);
  const previews = [
    {
      caption: 'browser session',
      code: 'open jobs.apple.com\n→ a real browser opens\n→ click around, or hand the\n  wheel to the agent',
    },
    {
      caption: 'session.har',
      code: 'GET  /api/v1/search?q=swift   200\nGET  /api/v1/job/114438118    200\n…\n41 requests recorded',
    },
    {
      caption: 'apple_jobs_client.py',
      code: '@dataclass\nclass Job:\n    id: str\n    title: str\n    location: str\n\nclass AppleJobsClient:\n    def search(self, q: str) -> list[Job]: ...',
    },
    {
      caption: 'your repo',
      code: '+ apple_jobs_client.py\n\nplain typed Python.\nno SDK to pin, no service\nto depend on.',
    },
  ];
  const preview = previews[active];
  return (
    <div className="bg-orange px-6 lg:px-10 py-12">
      <div className="grid md:grid-cols-[260px_1fr] gap-6 items-start">
        {/* tab list */}
        <div className="flex flex-col gap-2">
          {STEPS.map((s, i) => {
            const on = i === active;
            return (
              <button
                key={s.num}
                onClick={() => setActive(i)}
                className={`text-left rounded-lg border px-4 py-3 transition-all ${
                  on
                    ? 'border-ink bg-cream shadow-[3px_3px_0_0_var(--color-fd-primary)]'
                    : 'border-ink/12 bg-transparent hover:border-ink/30'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className={`font-mono text-xs ${on ? 'text-fd-primary' : 'text-ink-soft'}`}>
                    {s.num}
                  </span>
                  <span className="font-display text-lg tracking-tight">{s.title}</span>
                </div>
                {on && <p className="mt-1 text-xs leading-relaxed text-ink-soft">{s.body}</p>}
              </button>
            );
          })}
        </div>
        {/* code / output card — no terminal chrome */}
        <div className="rounded-xl overflow-hidden border border-ink/15 bg-fd-card">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-ink/10 bg-ink/[0.03]">
            <span className="font-mono text-[11px] text-ink-soft">{preview.caption}</span>
            <span className="font-display italic text-sm text-fd-primary leading-none">*</span>
          </div>
          <pre className="p-5 font-mono text-[12.5px] leading-relaxed text-ink whitespace-pre-wrap min-h-[210px]">
            {preview.code}
          </pre>
        </div>
      </div>
    </div>
  );
}

/* S5 — Pipeline node graph --------------------------------------------------
   Steps rendered as connected nodes on a flow, like a data pipeline / DAG.
   Connectors are pure CSS (a line between cards) so it stays responsive and
   needs no SVG measuring. */
function StepsPipeline() {
  return (
    <div className="bg-[#0d0a07] bg-dots px-6 lg:px-10 py-16">
      <div className="relative flex flex-col md:flex-row items-stretch gap-4 md:gap-0">
        {STEPS.map((s, i) => (
          <div key={s.num} className="relative flex-1 flex items-center">
            {/* connector to previous node */}
            {i > 0 && (
              <span
                aria-hidden="true"
                className="hidden md:block absolute right-full top-1/2 w-4 h-px bg-fd-primary/40"
              />
            )}
            <div className="group relative w-full rounded-xl border border-white/10 bg-[#1a1510] p-5 transition-colors hover:border-fd-primary/50">
              <h3 className="font-display text-xl tracking-tight text-[rgba(255,247,240,0.95)]">
                {s.title}
              </h3>
              <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-white/45">
                {s.body}
              </p>
            </div>
            {/* arrow into next node */}
            {i < STEPS.length - 1 && (
              <span
                aria-hidden="true"
                className="hidden md:flex items-center justify-center w-8 shrink-0 text-fd-primary"
              >
                →
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* S6 — Vertical rail --------------------------------------------------------
   Numbered nodes down a single left rail with a pink "progress" fill, like an
   onboarding checklist (ElevenLabs / Modal style). */
function StepsVerticalRail() {
  return (
    <div className="bg-cream px-6 lg:px-10 py-16">
      <div className="relative mx-auto max-w-2xl pl-12">
        {/* full rail + filled portion */}
        <div className="absolute left-[18px] top-2 bottom-2 w-px bg-ink/15" />
        <div className="absolute left-[18px] top-2 h-[62%] w-px bg-fd-primary" />
        <div className="flex flex-col gap-9">
          {STEPS.map((s, i) => {
            const done = i < 3;
            return (
              <div key={s.num} className="relative">
                <span
                  className={`absolute -left-12 flex size-9 items-center justify-center rounded-full font-mono text-xs ${
                    done
                      ? 'bg-fd-primary text-cream'
                      : 'bg-cream text-ink-soft border border-ink/20'
                  }`}
                >
                  {s.num}
                </span>
                <h3 className="font-display text-xl tracking-tight leading-none pt-1.5">
                  {s.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-soft">{s.body}</p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* S9 — Index cards ----------------------------------------------------------
   Stamped, slightly-rotated cards with neo-brutalist offset shadows. Playful
   and editorial — leans into the asterisk/serif personality. */
function StepsIndexCards() {
  const rotations = ['-2deg', '1.5deg', '-1deg', '2deg'];
  return (
    <div className="bg-mint px-6 lg:px-10 py-16">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {STEPS.map((s, i) => (
          <div
            key={s.num}
            className="bg-cream border-[1.5px] border-ink rounded-lg p-5 shadow-[4px_4px_0_0_var(--color-ink)] transition-transform hover:-translate-y-1"
            style={{ transform: `rotate(${rotations[i]})` }}
          >
            <div className="flex items-baseline justify-between">
              <span
                className="font-display italic text-3xl text-fd-primary leading-none"
                style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
              >
                {s.num}
              </span>
              <span className="font-display italic text-lg text-ink/25 select-none">*</span>
            </div>
            <h3 className="mt-4 font-display text-xl tracking-tight">{s.title}</h3>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">{s.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* S10 — Flow chips ----------------------------------------------------------
   One horizontal row of rounded chips connected by arrows. A compact process
   flow that reads left-to-right; wraps to a column on mobile. */
function StepsFlowChips() {
  return (
    <div className="bg-washed px-6 lg:px-10 py-16">
      <div className="flex flex-col md:flex-row md:items-stretch gap-4 md:gap-0">
        {STEPS.map((s, i) => (
          <div key={s.num} className="flex md:flex-1 items-center gap-4 md:gap-0">
            <div className="flex-1 rounded-2xl border border-ink/12 bg-cream px-5 py-5 shadow-[0_2px_0_0_color-mix(in_oklch,var(--color-ink)_10%,transparent)]">
              <div className="flex items-baseline gap-2.5">
                <span className="font-mono text-xs text-fd-primary">{s.num}</span>
                <h3 className="font-display text-xl tracking-tight">{s.title}</h3>
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">{s.body}</p>
            </div>
            {i < STEPS.length - 1 && (
              <span
                aria-hidden="true"
                className="shrink-0 self-center px-2 md:px-3 text-fd-primary font-display italic text-2xl rotate-90 md:rotate-0"
              >
                →
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* S11 — Color-block quarters ------------------------------------------------
   Four full-bleed panels in the brand pastels, each with a big number
   watermark. Bold, colorful, magazine-spread energy. */
function StepsColorBlocks() {
  const tones = ['bg-orange', 'bg-sky', 'bg-mint', 'bg-washed'];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
      {STEPS.map((s, i) => (
        <div
          key={s.num}
          className={`${tones[i]} relative overflow-hidden px-6 py-12 min-h-[220px] flex flex-col justify-end`}
        >
          <span
            aria-hidden="true"
            className="absolute -top-4 -right-2 font-display italic leading-none text-[7rem] text-ink/[0.06] select-none"
            style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
          >
            {s.num}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-soft">
            Step {s.num}
          </span>
          <h3 className="mt-2 font-display text-2xl tracking-tight">{s.title}</h3>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">{s.body}</p>
        </div>
      ))}
    </div>
  );
}

/* S12 — Staggered staircase -------------------------------------------------
   Cards in a 4-col grid, each pushed progressively further down so they
   literally descend like steps. */
function StepsStaircase() {
  const offsets = ['md:mt-0', 'md:mt-8', 'md:mt-16', 'md:mt-24'];
  return (
    <div className="bg-cream px-6 lg:px-10 py-16">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5 items-start">
        {STEPS.map((s, i) => (
          <div
            key={s.num}
            className={`${offsets[i]} rounded-xl border border-ink/12 bg-fd-card p-5 shadow-[0_2px_0_0_color-mix(in_oklch,var(--color-ink)_8%,transparent)]`}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs text-fd-primary">{s.num}</span>
              <span className="font-display italic text-sm text-ink/20 select-none">*</span>
            </div>
            <h3 className="mt-3 font-display text-xl tracking-tight">{s.title}</h3>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">{s.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* S13 — Alternating spine ---------------------------------------------------
   A vertical center spine; steps alternate left and right with a node dot on
   the line. Classic editorial timeline. */
function StepsSpine() {
  return (
    <div className="bg-washed px-6 lg:px-10 py-16">
      <div className="relative mx-auto max-w-3xl">
        {/* spine */}
        <div className="absolute left-4 md:left-1/2 top-2 bottom-2 w-px -translate-x-1/2 bg-ink/15" />
        <div className="flex flex-col gap-10">
          {STEPS.map((s, i) => {
            const right = i % 2 === 1;
            return (
              <div
                key={s.num}
                className={`relative pl-12 md:pl-0 md:grid md:grid-cols-2 md:gap-10 ${
                  right ? '' : ''
                }`}
              >
                {/* node */}
                <span className="absolute left-4 md:left-1/2 top-1 size-3 -translate-x-1/2 rounded-full bg-fd-primary ring-4 ring-[var(--color-washed)]" />
                <div
                  className={`${
                    right
                      ? 'md:col-start-2 md:pl-10 md:text-left'
                      : 'md:col-start-1 md:pr-10 md:text-right'
                  }`}
                >
                  <span className="font-mono text-xs text-fd-primary">{s.num}</span>
                  <h3 className="mt-1 font-display text-xl tracking-tight">{s.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{s.body}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* S14 — Spec-sheet rows -----------------------------------------------------
   Minimal hairline-separated rows with big monospace numbers. Reads like a
   technical spec / documentation table — very dev-native. */
function StepsSpecSheet() {
  return (
    <div className="bg-cream px-6 lg:px-10 py-12">
      <div className="mx-auto max-w-3xl divide-y divide-ink/10 border-y border-ink/10">
        {STEPS.map((s) => (
          <div key={s.num} className="grid grid-cols-[auto_1fr] md:grid-cols-[80px_180px_1fr] gap-x-6 gap-y-1 py-6 items-baseline">
            <span className="font-mono text-2xl text-fd-primary tabular-nums">{s.num}</span>
            <h3 className="font-display text-xl tracking-tight">{s.title}</h3>
            <p className="col-span-2 md:col-span-1 text-sm leading-relaxed text-ink-soft">
              {s.body}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ════════════════════════ WORKS WITH YOUR AGENT ════════════════════════════
   All variants share AGENTS + <BrandIcon> from components/brand-logos. The
   story everywhere: rae ships no model — it auto-detects and drives whichever
   coding agent you already have. */

/* A1 — Orbit ----------------------------------------------------------------
   The rae asterisk sits at the center; agent logos ride two dashed orbit
   rings. "Everything revolves around the agent you already use." */
function AgentsOrbit() {
  const inner = AGENTS.slice(0, 2);
  const outer = AGENTS.slice(2);
  return (
    <div className="bg-[#0d0a07] px-6 lg:px-10 py-16 flex flex-col items-center">
      <div className="relative size-[300px]">
        {/* rings */}
        <div className="absolute inset-[60px] rounded-full border border-dashed border-white/15" />
        <div className="absolute inset-0 rounded-full border border-dashed border-white/10" />
        {/* center: rae asterisk */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span
            className="font-display italic text-5xl text-fd-primary leading-none select-none"
            style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
          >
            *
          </span>
        </div>
        {/* inner ring agents (top & bottom) */}
        {inner.map((a, i) => (
          <div
            key={a.key}
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
            style={{ transform: `translate(-50%, -50%) rotate(${i * 180}deg) translateY(-90px) rotate(${-i * 180}deg)` }}
          >
            <span className="flex size-11 items-center justify-center rounded-full bg-cream shadow-lg">
              <BrandIcon agent={a} className="size-5 text-ink" />
            </span>
          </div>
        ))}
        {/* outer ring agents (left & right) */}
        {outer.map((a, i) => (
          <div
            key={a.key}
            className="absolute left-1/2 top-1/2"
            style={{ transform: `translate(-50%, -50%) rotate(${90 + i * 180}deg) translateY(-150px) rotate(${-(90 + i * 180)}deg)` }}
          >
            <span className="flex size-11 items-center justify-center rounded-full bg-cream shadow-lg">
              <BrandIcon agent={a} className="size-5 text-ink" />
            </span>
          </div>
        ))}
      </div>
      <p className="mt-8 max-w-md text-center font-mono text-xs text-white/50">
        rae drives the agent you already use — Claude Code, Cursor, Copilot, OpenCode, and more.
      </p>
    </div>
  );
}

/* A3 — Plug & socket --------------------------------------------------------
   Each agent is a "plug" that seats into a rae "socket" — a literal take on
   "plug in whatever agent you have." */
function AgentsSockets() {
  return (
    <div className="bg-washed px-6 lg:px-10 py-16">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {AGENTS.map((a) => (
          <div key={a.key} className="flex flex-col items-center">
            {/* plug */}
            <span className="flex size-14 items-center justify-center rounded-2xl bg-cream border border-ink/12 shadow-[0_2px_0_0_color-mix(in_oklch,var(--color-ink)_10%,transparent)]">
              <BrandIcon agent={a} className="size-6 text-ink" />
            </span>
            {/* pins */}
            <div className="flex gap-1.5 mt-0.5">
              <span className="h-3 w-1 rounded-b bg-ink/40" />
              <span className="h-3 w-1 rounded-b bg-ink/40" />
            </div>
            {/* socket */}
            <div className="mt-1 flex h-9 w-20 items-start justify-center gap-1.5 rounded-b-xl rounded-t-sm bg-ink pt-1.5">
              <span className="h-2.5 w-1 rounded-full bg-cream/30" />
              <span className="h-2.5 w-1 rounded-full bg-cream/30" />
            </div>
            <span className="mt-3 font-display text-base tracking-tight text-ink">{a.name}</span>
          </div>
        ))}
      </div>
      <p className="mt-10 text-center font-mono text-xs text-ink-soft">
        Plug in your agent — rae handles the rest.
      </p>
    </div>
  );
}

/* A4 — Boarding-pass handoff ------------------------------------------------
   Reuses the brand's ticket motif from the final CTA: HAR on the body, the
   chosen agent stamped in the stub, typed client as the destination. */
function AgentsHandoff() {
  return (
    <div className="bg-sky px-6 lg:px-10 py-16">
      <div className="mx-auto flex max-w-3xl flex-col md:flex-row overflow-hidden rounded-xl bg-[#0d0a07] shadow-[0_16px_48px_rgba(0,0,0,0.32)]">
        {/* body */}
        <div className="flex-1 p-7">
          <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-white/35">handoff</p>
          <div className="mt-3 flex items-center gap-3">
            <span className="font-mono text-lg text-white/85">session.har</span>
            <span className="text-fd-primary">→</span>
            <span className="font-display italic text-lg text-fd-primary">your agent</span>
            <span className="text-fd-primary">→</span>
            <span className="font-mono text-lg text-white/85">client.py</span>
          </div>
          <div className="mt-5 flex items-center gap-2.5">
            {AGENTS.map((a) => (
              <span key={a.key} className="flex size-8 items-center justify-center rounded-lg bg-white/[0.06]">
                <BrandIcon agent={a} className="size-4 text-white/75" />
              </span>
            ))}
            <span className="ml-1 font-mono text-[10px] text-white/35">+ more</span>
          </div>
        </div>
        {/* dashed seam */}
        <div className="relative w-px md:w-0 md:border-l md:border-dashed md:border-white/15">
          <span className="hidden md:block absolute -top-2 -left-2 size-4 rounded-full bg-[var(--color-sky)]" />
          <span className="hidden md:block absolute -bottom-2 -left-2 size-4 rounded-full bg-[var(--color-sky)]" />
        </div>
        {/* stub */}
        <div className="w-full md:w-44 p-7 flex flex-col justify-center">
          <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-white/35">driver</p>
          <p className="mt-2 font-display text-xl tracking-tight text-[rgba(255,247,240,0.95)]">
            Bring your own
          </p>
          <p className="mt-1 font-mono text-[10px] text-white/40">no model bundled</p>
        </div>
      </div>
    </div>
  );
}

/* A6 — Swappable slot -------------------------------------------------------
   One oversized "rae + [ slot ]" line; click/auto-cycle swaps the agent shown
   in the slot, framing rae as agent-agnostic. */
function AgentsSlot() {
  const [i, setI] = useState(0);
  const a = AGENTS[i];
  return (
    <div className="bg-orange px-6 lg:px-10 py-20">
      <div className="mx-auto max-w-3xl flex flex-col items-center">
        <div className="flex items-center gap-4 flex-wrap justify-center">
          <span
            className="font-display italic text-5xl md:text-6xl text-ink leading-none"
            style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
          >
            rae
          </span>
          <span className="font-display text-4xl md:text-5xl text-ink/30 leading-none">+</span>
          {/* slot */}
          <button
            onClick={() => setI((i + 1) % AGENTS.length)}
            className="group flex items-center gap-3 rounded-2xl border-[1.5px] border-dashed border-ink/30 bg-cream px-5 py-3 transition-colors hover:border-ink"
          >
            <BrandIcon agent={a} className="size-7 text-ink" />
            <span className="font-display text-2xl md:text-3xl tracking-tight text-ink">{a.name}</span>
          </button>
        </div>
        <div className="mt-7 flex items-center gap-2">
          {AGENTS.map((x, xi) => (
            <button
              key={x.key}
              onClick={() => setI(xi)}
              aria-label={x.name}
              className={`size-2 rounded-full transition-colors ${xi === i ? 'bg-fd-primary' : 'bg-ink/20'}`}
            />
          ))}
        </div>
        <p className="mt-6 font-mono text-xs text-ink-soft">Swap the agent — rae stays the same.</p>
      </div>
    </div>
  );
}

/* A8 — Sticker sheet --------------------------------------------------------
   Die-cut logo "stickers": white rounded chips, slight rotation, offset
   shadow. Tactile and playful, matches the neo-brutalist personality. */
function AgentsStickers() {
  const rot = ['-3deg', '2deg', '-1.5deg', '3deg'];
  return (
    <div className="bg-mint px-6 lg:px-10 py-16">
      <div className="flex flex-wrap items-center justify-center gap-6">
        {AGENTS.map((a, i) => (
          <div
            key={a.key}
            className="flex items-center gap-3 rounded-2xl border-[1.5px] border-ink bg-cream px-5 py-3.5 shadow-[4px_4px_0_0_var(--color-ink)] transition-transform hover:-translate-y-1"
            style={{ transform: `rotate(${rot[i]})` }}
          >
            <BrandIcon agent={a} className="size-6 text-ink" />
            <span className="font-display text-lg tracking-tight text-ink">{a.name}</span>
          </div>
        ))}
      </div>
      <p className="mt-10 text-center font-mono text-xs text-ink-soft">…and more — if it edits files, rae can drive it.</p>
    </div>
  );
}

/* A9 — Relay baton ----------------------------------------------------------
   A sequential band: capture hands the baton to your agent, which hands back
   the client. Tells the "rae orchestrates, the agent writes" story. */
function AgentsRelay() {
  return (
    <div className="bg-cream px-6 lg:px-10 py-16">
      <div className="mx-auto flex max-w-4xl flex-col md:flex-row items-stretch gap-4 md:gap-0">
        <RelayCard kicker="rae" title="Capture" body="Records the traffic into a HAR." />
        <RelayArrow />
        <div className="flex-1 rounded-xl border-[1.5px] border-ink bg-ink px-5 py-6 text-cream">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-cream/50">your agent writes it</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {AGENTS.map((a) => (
              <span key={a.key} className="flex size-9 items-center justify-center rounded-lg bg-cream/10">
                <BrandIcon agent={a} className="size-4.5 text-cream" />
              </span>
            ))}
          </div>
        </div>
        <RelayArrow />
        <RelayCard kicker="rae" title="Review" body="Plain typed client in your repo." />
      </div>
    </div>
  );
}

function RelayCard({ kicker, title, body }: { kicker: string; title: string; body: string }) {
  return (
    <div className="flex-1 rounded-xl border border-ink/15 bg-fd-card px-5 py-6">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-fd-primary">{kicker}</p>
      <h3 className="mt-2 font-display text-xl tracking-tight text-ink">{title}</h3>
      <p className="mt-1.5 text-[13px] leading-relaxed text-ink-soft">{body}</p>
    </div>
  );
}

function RelayArrow() {
  return (
    <span aria-hidden="true" className="shrink-0 self-center px-1 md:px-2 text-fd-primary font-display italic text-2xl rotate-90 md:rotate-0">
      →
    </span>
  );
}

/* A11 — Slot-machine reels --------------------------------------------------
   Three reels of agent logos behind a window; the message is that whatever you
   spin, rae lands on your agent. Arcade energy, on-brand asterisks. */
function AgentsReels() {
  return (
    <div className="bg-[#0d0a07] px-6 lg:px-10 py-16 flex flex-col items-center">
      <div className="flex items-stretch gap-3 rounded-2xl border-2 border-fd-primary/60 bg-[#161009] p-4 shadow-[0_0_40px_-8px_rgba(229,13,117,0.45)]">
        {[0, 1, 2].map((reel) => (
          <div
            key={reel}
            className="relative h-28 w-20 overflow-hidden rounded-lg bg-cream"
          >
            <div
              className="marquee-track absolute inset-x-0 flex flex-col items-center"
              style={{ animationName: 'agent-reel', animationDuration: `${6 + reel * 2}s`, width: '100%' }}
            >
              {[...AGENTS, ...AGENTS, ...AGENTS].map((a, i) => (
                <span key={i} className="flex h-20 w-full items-center justify-center">
                  <BrandIcon agent={a} className="size-9 text-ink" />
                </span>
              ))}
            </div>
            {/* center window highlight */}
            <div className="pointer-events-none absolute inset-x-0 top-1/2 h-20 -translate-y-1/2 border-y-2 border-fd-primary/30" />
          </div>
        ))}
      </div>
      <p className="mt-8 font-display text-2xl tracking-tight text-[rgba(255,247,240,0.95)]">
        Always lands on <em className="text-fd-primary">your</em> agent
      </p>
      <p className="mt-2 font-mono text-xs text-white/40">Claude Code · Cursor · Copilot · OpenCode · and more</p>
    </div>
  );
}

/* A12 — Conveyor belt -------------------------------------------------------
   A HAR box rides a belt into the rae machine; the agent stamps it and a typed
   client rolls out. Industrial "assembly line" metaphor. */
function AgentsConveyor() {
  return (
    <div className="bg-washed px-6 lg:px-10 py-16">
      <div className="mx-auto flex max-w-4xl items-center justify-between gap-3">
        <Crate label="session.har" tone="mono" />
        <BeltArrow />
        {/* the machine */}
        <div className="relative flex flex-col items-center rounded-2xl border-[1.5px] border-ink bg-ink px-6 py-5 text-cream shadow-[4px_4px_0_0_var(--color-fd-primary)]">
          <span
            className="font-display italic text-2xl leading-none"
            style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
          >
            rae
          </span>
          <div className="mt-2 flex gap-1.5">
            {AGENTS.map((a) => (
              <span key={a.key} className="flex size-6 items-center justify-center rounded bg-cream/10">
                <BrandIcon agent={a} className="size-3.5 text-cream" />
              </span>
            ))}
          </div>
          <span className="mt-2 font-mono text-[9px] uppercase tracking-[0.18em] text-cream/45">
            your agent inside
          </span>
        </div>
        <BeltArrow />
        <Crate label="client.py" tone="pink" />
      </div>
      {/* belt */}
      <div className="mx-auto mt-4 max-w-4xl h-2 rounded-full bg-ink/15 [background-image:repeating-linear-gradient(90deg,transparent_0_10px,color-mix(in_oklch,var(--color-ink)_20%,transparent)_10px_14px)]" />
    </div>
  );
}

function Crate({ label, tone }: { label: string; tone: 'mono' | 'pink' }) {
  return (
    <div className="flex flex-col items-center gap-2 shrink-0">
      <span
        className={`flex size-14 items-center justify-center rounded-lg border-[1.5px] ${
          tone === 'pink' ? 'border-fd-primary/50 bg-fd-primary/10' : 'border-ink/20 bg-cream'
        }`}
      >
        <span className="font-mono text-[9px] text-ink-soft">{tone === 'pink' ? '.py' : '.har'}</span>
      </span>
      <span className="font-mono text-[10px] text-ink-soft">{label}</span>
    </div>
  );
}

function BeltArrow() {
  return <span className="shrink-0 text-fd-primary font-display italic text-xl">→</span>;
}

/* A13 — Constellation -------------------------------------------------------
   Agents are stars connected by faint lines to a glowing rae core. Cosmic,
   premium, dark. */
function AgentsConstellation() {
  // Fixed positions (percentages) so it's deterministic and balanced.
  const pts = [
    { x: 22, y: 28 },
    { x: 78, y: 22 },
    { x: 18, y: 74 },
    { x: 80, y: 72 },
  ];
  return (
    <div className="relative bg-[#0d0a07] px-6 lg:px-10 py-20 overflow-hidden">
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        {pts.map((p, i) => (
          <line
            key={i}
            x1="50%"
            y1="50%"
            x2={`${p.x}%`}
            y2={`${p.y}%`}
            stroke="rgba(255,247,240,0.16)"
            strokeWidth={1}
            strokeDasharray="3 4"
          />
        ))}
      </svg>
      <div className="relative mx-auto h-64 max-w-2xl">
        {/* core */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
          <span
            className="font-display italic text-4xl text-fd-primary leading-none select-none drop-shadow-[0_0_16px_rgba(229,13,117,0.6)]"
            style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
          >
            *
          </span>
        </div>
        {/* stars */}
        {AGENTS.map((a, i) => (
          <div
            key={a.key}
            className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1.5"
            style={{ left: `${pts[i].x}%`, top: `${pts[i].y}%` }}
          >
            <span className="flex size-10 items-center justify-center rounded-full bg-cream shadow-[0_0_14px_rgba(255,247,240,0.25)]">
              <BrandIcon agent={a} className="size-5 text-ink" />
            </span>
            <span className="font-mono text-[10px] text-white/55 whitespace-nowrap">{a.name}</span>
          </div>
        ))}
      </div>
      <p className="relative mt-6 text-center font-mono text-xs text-white/40">
        rae orbits your stack — bring any agent.
      </p>
    </div>
  );
}

/* A14 — Rotary selector -----------------------------------------------------
   A dial with tick marks; a pointer indicates the active agent. Click an agent
   to "turn the dial." Tactile, mechanical. */
function AgentsDial() {
  const [i, setI] = useState(0);
  const n = AGENTS.length;
  const angle = (360 / n) * i;
  return (
    <div className="bg-orange px-6 lg:px-10 py-16 flex flex-col items-center">
      <div className="relative size-56">
        {/* ticks */}
        {Array.from({ length: 24 }).map((_, t) => (
          <span
            key={t}
            className="absolute left-1/2 top-1/2 h-1.5 w-px origin-bottom bg-ink/25"
            style={{ transform: `translate(-50%, -100%) rotate(${t * 15}deg) translateY(-104px)` }}
          />
        ))}
        {/* dial face */}
        <div className="absolute inset-6 rounded-full border-[1.5px] border-ink bg-cream shadow-[4px_4px_0_0_var(--color-ink)]" />
        {/* pointer */}
        <div
          className="absolute left-1/2 top-1/2 h-20 w-1 origin-bottom -translate-x-1/2 rounded-full bg-fd-primary transition-transform duration-500"
          style={{ transform: `translate(-50%, -100%) rotate(${angle}deg)` }}
        />
        {/* center logo */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="flex size-14 items-center justify-center rounded-full bg-ink">
            <BrandIcon agent={AGENTS[i]} className="size-7 text-cream" />
          </span>
        </div>
      </div>
      <div className="mt-6 flex items-center gap-2">
        {AGENTS.map((a, ai) => (
          <button
            key={a.key}
            onClick={() => setI(ai)}
            className={`rounded-full px-3 py-1.5 font-mono text-xs transition-colors ${
              ai === i ? 'bg-ink text-cream' : 'bg-cream text-ink-soft border border-ink/15'
            }`}
          >
            {a.name}
          </button>
        ))}
      </div>
      <p className="mt-5 font-mono text-xs text-ink-soft">Dial in your agent — rae adapts.</p>
    </div>
  );
}

/* A15 — Passport stamps -----------------------------------------------------
   Inked, rotated "stamps" over a faint document — "certified to run with."
   Tactile, leans into the boarding-pass/travel motif family. */
function AgentsStamps() {
  const rot = ['-8deg', '6deg', '-5deg', '9deg'];
  return (
    <div className="bg-cream bg-grid px-6 lg:px-10 py-16">
      <p className="text-center font-mono text-[10px] uppercase tracking-[0.25em] text-ink-soft">
        Certified to run with
      </p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-x-10 gap-y-8">
        {AGENTS.map((a, i) => (
          <div
            key={a.key}
            className="flex flex-col items-center gap-2 rounded-md border-2 border-fd-primary/60 px-5 py-3 text-fd-primary/80"
            style={{ transform: `rotate(${rot[i]})` }}
          >
            <BrandIcon agent={a} className="size-7" />
            <span className="font-mono text-[10px] uppercase tracking-[0.15em]">{a.name}</span>
            <span className="font-mono text-[8px] tracking-[0.2em] opacity-70">rae · approved</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* A16 — Isometric blocks ----------------------------------------------------
   Agent "blocks" with a faux-3D side, feeding into the taller rae block.
   Playful depth without real 3D. */
function AgentsBlocks() {
  return (
    <div className="bg-mint px-6 lg:px-10 py-16">
      <div className="flex flex-wrap items-end justify-center gap-5">
        {AGENTS.map((a) => (
          <div key={a.key} className="flex flex-col items-center gap-2">
            <div className="relative">
              <span className="flex size-16 items-center justify-center rounded-lg border-[1.5px] border-ink bg-cream shadow-[5px_5px_0_0_var(--color-ink)]">
                <BrandIcon agent={a} className="size-7 text-ink" />
              </span>
            </div>
            <span className="font-mono text-[10px] text-ink-soft">{a.name}</span>
          </div>
        ))}
        <span className="self-center pb-7 font-display italic text-2xl text-ink/40">→</span>
        <div className="flex flex-col items-center gap-2">
          <span className="flex size-20 items-center justify-center rounded-lg border-[1.5px] border-ink bg-fd-primary text-cream shadow-[5px_5px_0_0_var(--color-ink)]">
            <span
              className="font-display italic text-2xl leading-none"
              style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
            >
              rae
            </span>
          </span>
          <span className="font-mono text-[10px] text-ink-soft">typed client</span>
        </div>
      </div>
    </div>
  );
}

/* A17 — Command palette -----------------------------------------------------
   A ⌘K-style picker: "rae use <agent>" with each agent as a selectable result
   row. Speaks directly to the developer audience. */
function AgentsPalette() {
  const [sel, setSel] = useState(0);
  return (
    <div className="bg-[#0d0a07] px-6 lg:px-10 py-16">
      <div className="mx-auto max-w-md overflow-hidden rounded-xl border border-white/12 bg-[#161009] shadow-2xl">
        <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
          <span className="font-mono text-sm text-fd-primary">›</span>
          <span className="font-mono text-sm text-white/80">rae use </span>
          <span className="font-mono text-sm text-white/40">agent…</span>
          <span className="ml-auto rounded border border-white/15 px-1.5 py-0.5 font-mono text-[10px] text-white/40">
            ⌘K
          </span>
        </div>
        <ul className="py-1.5">
          {AGENTS.map((a, ai) => (
            <li key={a.key}>
              <button
                onMouseEnter={() => setSel(ai)}
                onClick={() => setSel(ai)}
                className={`flex w-full items-center gap-3 px-4 py-2.5 text-left ${
                  ai === sel ? 'bg-fd-primary/15' : ''
                }`}
              >
                <BrandIcon agent={a} className="size-4 text-white/85" />
                <span className="font-mono text-[13px] text-white/90">{a.name}</span>
                <span className="ml-auto font-mono text-[10px] text-white/30">{a.note}</span>
                {ai === sel && <span className="font-mono text-[11px] text-fd-primary">↵</span>}
              </button>
            </li>
          ))}
        </ul>
        <div className="border-t border-white/10 px-4 py-2 font-mono text-[10px] text-white/35">
          rae ships no model — it drives the one you pick.
        </div>
      </div>
    </div>
  );
}

/* A18 — Filmstrip -----------------------------------------------------------
   Agents as frames in a film strip with sprocket holes. Sequential, editorial,
   a little cinematic. */
function AgentsFilmstrip() {
  return (
    <div className="bg-[#0d0a07] px-6 lg:px-10 py-16">
      <div className="mx-auto max-w-4xl overflow-hidden rounded-md bg-[#1a1510]">
        {/* top sprockets */}
        <Sprockets />
        <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-white/10 border-y border-white/10">
          {AGENTS.map((a) => (
            <div key={a.key} className="flex flex-col items-center gap-3 px-4 py-8">
              <BrandIcon agent={a} className="size-9 text-[rgba(255,247,240,0.92)]" />
              <span className="font-mono text-[11px] text-white/55">{a.name}</span>
            </div>
          ))}
        </div>
        <Sprockets />
      </div>
      <p className="mt-6 text-center font-mono text-xs text-white/40">
        Every agent, same rae workflow.
      </p>
    </div>
  );
}

function Sprockets() {
  return (
    <div className="flex justify-between px-3 py-2">
      {Array.from({ length: 16 }).map((_, i) => (
        <span key={i} className="h-2.5 w-3 rounded-sm bg-[#0d0a07]" />
      ))}
    </div>
  );
}

/* A19 — Circuit board -------------------------------------------------------
   Agent pads wired with PCB traces into a central rae chip. Hardware/firmware
   vibe that fits the "engineer" identity. */
function AgentsCircuit() {
  const pads = [
    { x: 14, y: 24 },
    { x: 86, y: 24 },
    { x: 14, y: 76 },
    { x: 86, y: 76 },
  ];
  return (
    <div className="relative bg-[#0b1410] px-6 lg:px-10 py-20 overflow-hidden">
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        {pads.map((p, i) => (
          <g key={i} stroke="rgba(120,240,180,0.30)" strokeWidth={1.5} fill="none">
            <path d={`M ${p.x}% ${p.y}% H 50% V 50%`} />
            <circle cx={`${p.x}%`} cy={`${p.y}%`} r={3} fill="rgba(120,240,180,0.5)" stroke="none" />
          </g>
        ))}
      </svg>
      <div className="relative mx-auto h-60 max-w-2xl">
        {/* chip */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex size-20 items-center justify-center rounded-lg border border-[rgba(120,240,180,0.5)] bg-[#0d1a14]">
          <span
            className="font-display italic text-2xl leading-none text-[rgba(120,240,180,0.95)]"
            style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
          >
            rae
          </span>
        </div>
        {AGENTS.map((a, i) => (
          <div
            key={a.key}
            className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1.5"
            style={{ left: `${pads[i].x}%`, top: `${pads[i].y}%` }}
          >
            <span className="flex size-10 items-center justify-center rounded-md bg-cream">
              <BrandIcon agent={a} className="size-5 text-ink" />
            </span>
            <span className="font-mono text-[9px] text-[rgba(120,240,180,0.7)] whitespace-nowrap">{a.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* A20 — Split-flap board ----------------------------------------------------
   Airport/train departure-board aesthetic: flap tiles that read the agent
   names, framing rae as the universal "departure" to a typed client. */
function AgentsSplitFlap() {
  return (
    <div className="bg-[#0d0a07] px-6 lg:px-10 py-16">
      <div className="mx-auto max-w-2xl space-y-2.5">
        <div className="flex items-center justify-between px-1 pb-1 font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
          <span>agent</span>
          <span>status</span>
        </div>
        {AGENTS.map((a) => (
          <div key={a.key} className="flex items-center gap-3">
            <span className="flex size-8 items-center justify-center rounded bg-white/[0.06]">
              <BrandIcon agent={a} className="size-4 text-white/85" />
            </span>
            {/* flap tiles for the name */}
            <div className="flex gap-px">
              {a.name.toUpperCase().slice(0, 14).split('').map((ch, ci) => (
                <span
                  key={ci}
                  className="flex h-7 w-5 items-center justify-center rounded-[3px] bg-[#1c1c1c] font-mono text-[13px] text-[rgba(255,247,240,0.92)] shadow-[inset_0_-1px_0_rgba(0,0,0,0.6)]"
                >
                  {ch === ' ' ? ' ' : ch}
                </span>
              ))}
            </div>
            <span className="ml-auto font-mono text-[11px] text-fd-primary">SUPPORTED</span>
          </div>
        ))}
        <p className="pt-3 text-center font-mono text-[11px] text-white/40">
          …and more — every departure ends in a typed client.
        </p>
      </div>
    </div>
  );
}
