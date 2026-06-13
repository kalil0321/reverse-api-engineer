import { BrandIcon } from './brand-icon';
import { CLIENTS } from './clients';

// "Sticker wall" directory of clients & CLIs built with rae.
//
// NOT YET WIRED INTO THE SITE. The visual design is final, but the data source
// and "Submit your client" submission flow are still TBD. Drop <ShareDirectory />
// into a route/section once that logic exists.

const DISPLAY = "'opsz' 144, 'SOFT' 100, 'WONK' 1";
const ROT = [-3, 2, -1.5, 3, -2.5, 1.5, -2, 2.5, -1, 3, -3, 1, -2];
const TAPE_ROT = [-5, 4, -3, 6, -4, 3, -6, 5, -2, 4, -5, 3, -4];
const PAPER = ['#fff27a', '#ffb3d1', '#c4edd0', '#bfe3ff', '#ffd6a5', '#e9d5ff'];

// A strip of translucent scotch tape, hand-placed across the top of a note.
function Tape({ angle }: { angle: number }) {
  return (
    <span
      aria-hidden
      className="absolute left-1/2 -top-2.5 -translate-x-1/2"
      style={{
        width: 80,
        height: 22,
        rotate: `${angle}deg`,
        background:
          'linear-gradient(135deg, rgba(255,255,255,0.6) 0%, rgba(238,232,216,0.28) 45%, rgba(255,255,255,0.5) 100%)',
        boxShadow: '0 1px 2px rgba(20,14,8,0.10)',
        borderLeft: '1px solid rgba(255,255,255,0.6)',
        borderRight: '1px solid rgba(255,255,255,0.6)',
      }}
    />
  );
}

export function ShareDirectory() {
  return (
    <section className="bg-cream text-ink">
      <div className="mx-auto max-w-7xl px-6 lg:px-10 py-20 md:py-28">
        <div className="text-center mb-14">
          <h1
            className="font-display italic text-[clamp(2.4rem,6vw,4rem)] tracking-[-0.045em] leading-[0.9]"
            style={{ fontVariationSettings: DISPLAY, fontWeight: 400 }}
          >
            Look what people <span style={{ color: 'var(--color-fd-primary)' }}>reverse-engineered.</span>
          </h1>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-x-6 gap-y-12">
          {CLIENTS.map((c, i) => (
            <a
              key={c.slug}
              href="#"
              className="group relative block no-underline text-[#241c14] transition-transform duration-200 hover:!rotate-0 hover:-translate-y-1.5"
              style={{
                rotate: `${ROT[i % ROT.length]}deg`,
                background: PAPER[i % PAPER.length],
                padding: '20px 16px 16px',
                boxShadow: '5px 6px 14px rgba(20,14,8,0.18)',
              }}
            >
              <Tape angle={TAPE_ROT[i % TAPE_ROT.length]} />
              <div className="flex items-center gap-2.5 mb-2">
                <BrandIcon
                  domain={c.domain}
                  monogram={c.monogram}
                  accent={c.accent}
                  size={20}
                  className="size-9 rounded-md"
                />
                <span className="text-lg font-semibold tracking-[-0.01em] text-[#241c14]">{c.service}</span>
              </div>
              <p className="text-[13px] leading-snug text-[#241c14]/80 min-h-[3.5em]">{c.blurb}</p>
              <div className="mt-3 pt-2.5 border-t border-[#241c14]/20 flex items-center justify-between font-mono text-[10px] text-[#241c14]/70">
                <span>{c.author}</span>
                <span>★ {c.stars}</span>
              </div>
            </a>
          ))}

          {/* share CTA note */}
          <a
            href="#"
            className="group relative grid place-items-center no-underline text-[#241c14] transition-transform duration-200 hover:!rotate-0 hover:-translate-y-1.5"
            style={{
              rotate: `${ROT[CLIENTS.length % ROT.length]}deg`,
              background: '#fffdf8',
              padding: '20px 16px 16px',
              minHeight: 176,
              boxShadow: '5px 6px 14px rgba(20,14,8,0.18)',
              border: '2px dashed rgba(36,28,20,0.35)',
            }}
          >
            <Tape angle={TAPE_ROT[CLIENTS.length % TAPE_ROT.length]} />
            <div className="text-center">
              <span
                className="font-display italic text-3xl leading-none"
                style={{ fontVariationSettings: DISPLAY, color: 'var(--color-fd-primary)' }}
              >
                +
              </span>
              <p className="text-[15px] font-semibold mt-1.5">Share your client</p>
              <p className="font-mono text-[10px] uppercase tracking-widest text-[#241c14]/55 mt-1">opens a PR</p>
            </div>
          </a>
        </div>
      </div>
    </section>
  );
}
