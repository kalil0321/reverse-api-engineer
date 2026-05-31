'use client';

import { Scales, HardDrives, EyeSlash, TerminalWindow } from '@phosphor-icons/react';

/* Feature marquee — a seamless horizontal band of trust signals under the hero.

   Four parallel "good citizen" claims, each with a leading Phosphor duotone
   icon and the brand asterisk as the divider.

   Seamless-loop rules (both required, easy to get wrong):
   1. Spacing is baked into each cell (pr-10), NOT a flex `gap` on the animated
      track — a gap between the two duplicated halves breaks periodicity and you
      get a visible stutter every loop.
   2. One half of the track must be wider than the viewport, else the last tag
      scrolls off and leaves an empty gap before the duplicate catches up. With
      only four short tags we repeat the set REPS times per half to guarantee
      that on any screen width. */
const FEATURES = [
  { Icon: Scales, label: 'MIT licensed' },
  { Icon: HardDrives, label: 'Runs locally' },
  { Icon: EyeSlash, label: 'No telemetry' },
  { Icon: TerminalWindow, label: 'Works with agents' },
];

const REPS = 4;

export function FeatureMarquee() {
  const half = Array.from({ length: REPS }, () => FEATURES).flat();
  const cells = [...half, ...half];
  return (
    <section className="marquee-viewport overflow-hidden border-y border-[rgba(255,247,240,0.1)] bg-[#1f1f1f] py-5 dark:border-transparent dark:bg-black">
      <div className="marquee-track flex" style={{ animationDuration: `${REPS * 30}s` }}>
        {cells.map(({ Icon, label }, i) => (
          <span key={i} className="flex shrink-0 items-center gap-10 pr-10">
            <span className="flex items-center gap-2 whitespace-nowrap text-[rgba(255,247,240,0.82)]">
              <Icon weight="duotone" className="size-[18px] text-[rgba(255,247,240,0.95)]" />
              <span className="font-mono text-sm">{label}</span>
            </span>
            <span className="select-none font-display text-lg italic leading-none text-fd-primary/70">
              *
            </span>
          </span>
        ))}
      </div>
    </section>
  );
}
