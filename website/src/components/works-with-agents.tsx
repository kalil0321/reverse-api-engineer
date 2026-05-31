import { AGENTS, BrandIcon } from '@/components/brand-logos';

/* Works-with-your-agent — split-flap departure board.

   rae ships no model of its own; it auto-detects and drives whichever coding
   agent you already have. The airport split-flap board frames each supported
   agent as a "departure" that always arrives at a typed client. Ties into the
   brand's existing travel/boarding-pass motif (see the final-CTA ticket). */
export function WorksWithAgents() {
  return (
    <section className="bg-mint relative overflow-hidden">
      <span
        aria-hidden="true"
        className="absolute top-12 right-16 hidden md:block font-display italic text-5xl text-fd-primary/30 select-none rotate-12"
      >
        *
      </span>

      <div className="relative mx-auto max-w-7xl px-6 lg:px-10 py-24 md:py-32">
        {/* Split-flap board — the board itself stays dark (like a real
            departure display) so it reads as a physical object on any page bg. */}
        <div className="mx-auto max-w-2xl space-y-2.5 rounded-2xl bg-[#0d0a07] p-6 md:p-8 shadow-[0_20px_60px_-30px_rgba(0,0,0,0.5)]">
          <div className="flex items-center justify-between px-1 pb-1 font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
            <span>agent</span>
            <span>status</span>
          </div>
          {AGENTS.map((a) => (
            <div key={a.key} className="flex items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded bg-white/[0.06]">
                <BrandIcon agent={a} className="size-4 text-white/85" />
              </span>
              {/* flap tiles spelling the agent name */}
              <div className="flex gap-px overflow-hidden">
                {a.name.toUpperCase().slice(0, 16).split('').map((ch, ci) => (
                  <span
                    key={ci}
                    className="flex h-7 w-5 items-center justify-center rounded-[3px] bg-[#1c1c1c] font-mono text-[13px] text-[rgba(255,247,240,0.92)] shadow-[inset_0_-1px_0_rgba(0,0,0,0.6)]"
                  >
                    {ch === ' ' ? ' ' : ch}
                  </span>
                ))}
              </div>
              <span className="ml-auto shrink-0 font-mono text-[11px] text-fd-primary">SUPPORTED</span>
            </div>
          ))}
        </div>

        <h2 className="mx-auto mt-12 max-w-2xl text-center font-display text-2xl md:text-3xl tracking-tight text-ink">
          Works with the agent <em className="text-fd-primary">you already use.</em>
        </h2>
      </div>
    </section>
  );
}
