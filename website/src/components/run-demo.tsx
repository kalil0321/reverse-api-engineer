'use client';

import { useEffect, useRef, useState } from 'react';

/* Real agent runs of rae 0.15.0 with Sonnet 5.5, recorded from the CLI and the agent's browser.
   Each video plays the run sped up and says by how much; the numbers below are the run's own. */
const DEMOS = [
  {
    id: 'steam',
    label: 'Steam charts',
    prompt: 'Top 100 games on store.steampowered.com/charts: name, live players, 24h peak',
    result: '100 games from two undocumented Steam endpoints · 1m02s · $0.11',
  },
  {
    id: 'luma',
    label: 'Luma events',
    prompt: 'Every AI event in SF this week on luma.com/sf: name, time, venue, link',
    result: "This week's SF AI events from Luma's discover API · 50s · $0.12",
  },
  {
    id: 'espn',
    label: 'ESPN scores',
    prompt: "Last night's NBA scores on espn.com/nba/scoreboard: teams, score, status",
    result: "Last night's games from ESPN's scoreboard API · 23s · $0.07",
  },
] as const;

export function RunDemo() {
  const [active, setActive] = useState(0);
  const video = useRef<HTMLVideoElement>(null);
  const demo = DEMOS[active];

  // Playback starts here, not from an autoplay attribute, so nothing moves before the
  // reduced-motion preference is known. A browser that blocks it leaves the controls to the visitor.
  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!reduce.matches) video.current?.play().catch(() => {});
    const onChange = () => {
      if (reduce.matches) video.current?.pause();
    };
    reduce.addEventListener('change', onChange);
    return () => reduce.removeEventListener('change', onChange);
  }, [active]);

  return (
    <div className="mx-auto w-full max-w-5xl">
      <div role="group" aria-label="Demo runs" className="flex flex-wrap justify-center gap-2">
        {DEMOS.map((d, i) => (
          <button
            key={d.id}
            type="button"
            aria-pressed={i === active}
            onClick={() => setActive(i)}
            className={i === active ? 'run-demo-tab run-demo-tab-active' : 'run-demo-tab'}
          >
            {d.label}
          </button>
        ))}
      </div>

      <div className="run-demo-frame mt-6 sm:mt-8">
        <video
          key={demo.id}
          ref={video}
          className="block h-auto w-full"
          src={`/demo/${demo.id}.mp4`}
          poster={`/demo/${demo.id}.jpg`}
          width={1920}
          height={1080}
          controls
          muted
          loop
          playsInline
          preload="metadata"
          aria-label={`rae run: ${demo.prompt}`}
        />
      </div>

      <p className="mt-5 text-center font-mono text-[11px] leading-relaxed text-ink sm:text-xs">
        <span className="text-fd-primary">›</span> {demo.prompt}
      </p>
      <p className="mt-1 text-center text-xs text-ink-soft">{demo.result}</p>
    </div>
  );
}
