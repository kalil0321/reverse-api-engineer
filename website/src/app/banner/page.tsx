export default function BannerPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-[color-mix(in_oklch,var(--color-ink)_6%,transparent)] p-8">
      {/* Outer crop guide — a dashed outline 4px larger than the frame so
          the user can see exactly what to screenshot. */}
      <div className="relative" style={{ width: 1280, height: 640 }}>
        {/* Crop guide */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -inset-1 border-2 border-dashed border-fd-primary/50 rounded-[2px]"
        />

        {/* The actual 1280×640 banner content */}
        <div
          className="relative w-full h-full bg-color-mesh overflow-hidden flex items-center justify-center"
        >
          {/* Ambient asterisks */}
          <span
            aria-hidden="true"
            className="absolute top-16 right-24 font-display italic select-none -rotate-12 text-fd-primary/45"
            style={{ fontSize: 96 }}
          >
            *
          </span>
          <span
            aria-hidden="true"
            className="absolute bottom-20 left-24 font-display italic select-none rotate-12 text-ink/20"
            style={{ fontSize: 72 }}
          >
            *
          </span>

          {/* Headline + logo, vertically stacked, centered */}
          <div className="relative flex flex-col items-center text-center gap-12">
            <h1
              className="font-display text-ink leading-[0.95]"
              style={{
                fontSize: 96,
                fontVariationSettings: "'opsz' 144, 'SOFT' 30, 'WONK' 1",
                fontWeight: 500,
                letterSpacing: '-0.045em',
              }}
            >
              Turn any website<br />
              <em
                className="italic"
                style={{
                  fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
                  fontWeight: 400,
                  color: 'var(--color-fd-primary)',
                }}
              >
                into an API.
              </em>
            </h1>

            {/* rae logo — large, centered under the headline */}
            <div className="flex items-baseline gap-3">
              <span
                className="font-display select-none leading-none inline-block italic"
                style={{
                  fontSize: 88,
                  color: 'var(--color-fd-primary)',
                  fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
                }}
                aria-hidden="true"
              >
                *
              </span>
              <span
                className="font-display italic text-ink leading-none"
                style={{
                  fontSize: 96,
                  letterSpacing: '-0.05em',
                  fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
                }}
              >
                rae
              </span>
            </div>
          </div>
        </div>

        {/* Tiny caption under the frame — tells the user what to do */}
        <p className="absolute -bottom-9 left-0 right-0 text-center font-mono text-[11px] uppercase tracking-widest text-ink-soft">
          1280 × 640 · screenshot the dashed rectangle
        </p>
      </div>
    </main>
  );
}
