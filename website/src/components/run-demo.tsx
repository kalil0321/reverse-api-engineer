'use client';

import { useEffect, useRef, useState } from 'react';
import { useTheme } from 'next-themes';

// The CLI demos show sped-up runs of rae 0.15.0 with Sonnet 5.5. Their timings and costs are from those runs.
const DEMOS = [
  {
    id: 'steam',
    label: 'Steam charts',
    prompt: 'Top 100 games on store.steampowered.com/charts: name, live players, 24h peak',
    result: '100 games from two undocumented Steam endpoints · 1m02s · $0.11',
  },
  {
    id: 'desktop',
    label: 'RAE Desktop',
    prompt: 'Find Airbnb stays in New York City with prices and ratings',
    result: 'RAE Desktop records the requests and builds a Python client that returns 18 stays.',
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
  const { resolvedTheme } = useTheme();
  const demo = DEMOS[active];
  const media = demo.id === 'desktop' ? `desktop-${resolvedTheme === 'dark' ? 'dark' : 'light'}` : demo.id;

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
  }, [media]);

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
          key={media}
          ref={video}
          className="block h-auto w-full"
          src={`/demo/${media}.mp4`}
          poster={`/demo/${media}.jpg`}
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
