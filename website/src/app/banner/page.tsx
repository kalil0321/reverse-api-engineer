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
          {/* Logo — top-left corner */}
          <div className="absolute top-10 left-12 flex items-baseline gap-2">
            <span
              className="font-display select-none leading-none inline-block italic"
              style={{
                fontSize: 56,
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
                fontSize: 64,
                letterSpacing: '-0.05em',
                fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
              }}
            >
              rae
            </span>
          </div>

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

          {/* Headline — centered */}
          <h1
            className="relative font-display text-ink leading-[0.95] text-center"
            style={{
              fontSize: 104,
              fontVariationSettings: "'opsz' 144, 'SOFT' 30, 'WONK' 1",
              fontWeight: 500,
              letterSpacing: '-0.045em',
            }}
          >
            Turn websites<br />
            <em
              className="italic relative inline-block text-ink"
              style={{
                fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
                fontWeight: 400,
                paddingBottom: '0.08em',
              }}
            >
              into APIs.
              <span
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  bottom: '-0.02em',
                  height: 6,
                  background: 'var(--color-fd-primary)',
                  borderRadius: 2,
                }}
              />
            </em>
          </h1>
        </div>

        {/* Tiny caption under the frame — tells the user what to do */}
        <p className="absolute -bottom-9 left-0 right-0 text-center font-mono text-[11px] uppercase tracking-widest text-ink-soft">
          1280 × 640 · screenshot the dashed rectangle
        </p>
      </div>
    </main>
  );
}
