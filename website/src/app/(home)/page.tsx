import Link from 'next/link';
import { ArrowRightIcon } from 'lucide-react';
import { githubUrl } from '@/lib/shared';
import { HeroCyclingPhrase } from '@/components/hero-cycling-phrase';
import { InstallCommand } from '@/components/install-command';
import { BuiltInTheOpen } from '@/components/built-in-the-open';

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2c-3.2.7-3.87-1.37-3.87-1.37-.52-1.33-1.27-1.69-1.27-1.69-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.75 2.67 1.25 3.32.96.1-.74.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.47.11-3.06 0 0 .96-.31 3.15 1.18a10.94 10.94 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.77.11 3.06.73.81 1.18 1.84 1.18 3.1 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

export default function HomePage() {
  return (
    <main className="flex-1">
      <div className="flex flex-col h-[calc(100svh-3.5rem)] min-h-[640px]">
        <Hero />
        <Marquee />
      </div>
      <HowItWorks />
      <BuiltInTheOpen />
      <FinalCTA />
    </main>
  );
}

/* ───────────────────────────── Hero ───────────────────────────── */

function Hero() {
  return (
    <section className="relative overflow-hidden flex-1 flex items-center">
      <span className="absolute top-10 right-10 hidden md:block font-display italic text-6xl text-fd-primary/45 select-none -rotate-12">*</span>
      <span className="absolute bottom-20 left-10 hidden md:block font-display italic text-4xl text-ink/20 select-none rotate-12">*</span>

      <div className="relative w-full mx-auto max-w-7xl px-6 lg:px-10 py-12">
        <div className="mx-auto max-w-5xl text-center">
          <InstallCommand />

          <h1 className="hero-display mt-8">
            Browse a site.<br />
            <HeroCyclingPhrase />
          </h1>

          <div className="mt-10 inline-flex flex-wrap items-center justify-center gap-3">
            <Link href="/docs" className="btn-primary">
              Read the docs
              <ArrowRightIcon className="size-4" />
            </Link>
            <Link href={githubUrl} target="_blank" className="btn-secondary">
              <GithubIcon className="size-4" />
              View on GitHub
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────────────── Marquee ─────────────────────────── */

function Marquee() {
  const tags = [
    'MIT licensed',
    'Chrome DevTools MCP',
    'HAR capture',
    'typed clients',
    'agent-ready',
  ];
  const items = [...tags, ...tags];
  return (
    <section
      className="py-5 border-y overflow-hidden
        bg-[#1f1f1f] border-[rgba(255,247,240,0.1)]
        dark:bg-black dark:border-transparent"
    >
      <div className="marquee gap-12">
        {items.map((t, i) => (
          <div key={i} className="flex items-center gap-12 shrink-0">
            <span className="font-mono text-sm whitespace-nowrap text-[rgba(255,247,240,0.8)]">{t}</span>
            <span className="font-display italic text-lg select-none text-[rgba(255,247,240,0.28)]">*</span>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ─────────────────────────── How it works ───────────────────────── */

function HowItWorks() {
  const steps = [
    { num: '01', title: 'Browse', body: 'Open the CLI. Drive the browser, or let the agent.' },
    { num: '02', title: 'Capture', body: 'HAR records every request, header, and body.' },
    { num: '03', title: 'Generate', body: 'Claude reads the HAR. Writes a typed client.' },
    { num: '04', title: 'Review', body: 'Audit the output, then commit it like any code.' },
  ];
  return (
    <section className="bg-orange relative overflow-hidden min-h-[100svh] flex items-center">
      {/* Ambient code stream backdrop — pushed hard to the right edge */}
      <pre
        aria-hidden="true"
        className="code-stream-pre absolute inset-y-0 right-0 hidden md:block w-[42%] lg:w-[40%] p-10 overflow-hidden"
        style={{
          maskImage:
            'linear-gradient(to right, transparent 0%, black 55%, black 92%, transparent 100%)',
          WebkitMaskImage:
            'linear-gradient(to right, transparent 0%, black 55%, black 92%, transparent 100%)',
        }}
      >
{`from dataclasses import dataclass
import httpx

@dataclass
class Job:
    id: str
    title: str
    location: str

class AppleJobsClient:
    BASE = "https://jobs.apple.com/api/v1"

    def search(self, query: str, *, page: int = 0):
        r = self._http.get(
            f"{self.BASE}/search",
            params={"q": query, "page": page},
        )
        r.raise_for_status()
        return [Job(**row) for row in r.json()["jobs"]]

    def detail(self, job_id: str) -> Job:
        r = self._http.get(f"{self.BASE}/job/{job_id}")
        return Job(**r.json())

@dataclass
class SearchResult:
    total: int
    page: int
    jobs: list[Job]

def authenticate(token: str) -> httpx.Client:
    return httpx.Client(headers={"Authorization": f"Bearer {token}"})`}
      </pre>

      <div className="relative w-full mx-auto max-w-7xl px-6 lg:px-10 py-24 md:py-36">
        <div className="max-w-2xl">
          <p className="eyebrow text-ink-soft">How it works</p>
          <h2 className="section-display mt-3">
            Four steps. <em>Zero glue code.</em>
          </h2>
        </div>

        <ol className="mt-14 grid md:grid-cols-4 gap-px bg-ink/10 rounded-2xl overflow-hidden border border-ink/10 shadow-[0_20px_60px_-30px_rgba(0,0,0,0.15)]">
          {steps.map((s) => (
            <li key={s.num} className="bg-cream p-7 flex flex-col min-h-[180px]">
              <span className="font-mono text-xs text-ink uppercase tracking-widest">
                {s.num} / 04
              </span>
              <h3 className="mt-8 font-display text-3xl tracking-tight text-ink">{s.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/* ────────────────────────── Final CTA ──────────────────────────── */

function FinalCTA() {
  return (
    <section className="relative overflow-hidden bg-sky min-h-[100svh] flex items-center">
      <div className="absolute inset-0 bg-scanlines pointer-events-none" />
      <span
        aria-hidden="true"
        className="absolute top-12 right-16 hidden md:block font-display italic text-5xl text-fd-primary/40 select-none -rotate-12"
      >
        *
      </span>
      <span
        aria-hidden="true"
        className="absolute bottom-14 left-10 hidden md:block font-display italic text-4xl text-ink/15 select-none rotate-12"
      >
        *
      </span>

      <div className="relative w-full mx-auto max-w-6xl px-6 lg:px-10 py-28 md:py-40">
        <div className="grid md:grid-cols-[1.1fr_1fr] gap-12 md:gap-16 items-center">
          {/* Left: headline + CTAs */}
          <div>
            <h2 className="hero-display text-left">
              Skip the<br /><em>scraping.</em>
            </h2>
            <p className="mt-8 max-w-md text-base md:text-lg text-ink-soft leading-relaxed">
              One install. One command. A working Python client before
              your coffee gets cold.
            </p>
            <div className="mt-10 inline-flex flex-wrap items-center gap-3">
              <Link href="/docs/quick-start" className="btn-primary">
                Get started
                <ArrowRightIcon className="size-4" />
              </Link>
              <Link href={githubUrl} target="_blank" className="btn-secondary">
                <GithubIcon className="size-4" />
                View on GitHub
              </Link>
            </div>
          </div>

          <BoardingPass />
        </div>
      </div>
    </section>
  );
}

function BoardingPass() {
  const BARS = [4, 2, 5, 1, 3, 4, 2, 1, 3, 2, 5, 1, 3, 2];
  return (
    <div
      style={{
        display: 'flex',
        borderRadius: 12,
        overflow: 'hidden',
        boxShadow: '0 16px 48px rgba(0,0,0,0.32), 0 4px 12px rgba(0,0,0,0.16)',
        fontFamily: 'var(--font-jetbrains-mono, monospace)',
      }}
    >
      {/* Main body */}
      <div style={{ flex: 1, background: '#0d0a07', padding: '22px 22px 22px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
          <div>
            <p style={{ fontSize: 7, letterSpacing: '0.22em', color: 'rgba(255,247,240,0.3)', textTransform: 'uppercase', marginBottom: 6 }}>From</p>
            <p style={{ fontSize: 26, fontWeight: 800, color: 'rgba(255,247,240,0.9)', letterSpacing: '-0.04em', lineHeight: 1 }}>RAW</p>
            <p style={{ fontSize: 7, color: 'rgba(255,247,240,0.2)', letterSpacing: '0.15em', marginTop: 5 }}>HTTP CHAOS</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', paddingTop: 14, gap: 4 }}>
            <div style={{ height: 1, width: 20, background: 'rgba(229,13,117,0.4)' }} />
            <span style={{ color: '#e50d75', fontSize: 18, lineHeight: 1 }}>→</span>
          </div>
          <div style={{ textAlign: 'right' }}>
            <p style={{ fontSize: 7, letterSpacing: '0.22em', color: 'rgba(255,247,240,0.3)', textTransform: 'uppercase', marginBottom: 6 }}>To</p>
            <p style={{ fontSize: 26, fontWeight: 800, color: '#e50d75', letterSpacing: '-0.04em', lineHeight: 1 }}>TYPED</p>
            <p style={{ fontSize: 7, color: 'rgba(255,247,240,0.2)', letterSpacing: '0.15em', marginTop: 5 }}>PYTHON CLIENT</p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 24, borderTop: '1px solid rgba(255,247,240,0.07)', paddingTop: 16 }}>
          {[['GATE', 'PY'], ['FLIGHT', 'rae-gen'], ['DURATION', '5 MIN']].map(([k, v]) => (
            <div key={k}>
              <p style={{ fontSize: 6.5, letterSpacing: '0.22em', color: 'rgba(255,247,240,0.26)', textTransform: 'uppercase', marginBottom: 5 }}>{k}</p>
              <p style={{ fontSize: 12, color: 'rgba(255,247,240,0.8)' }}>{v}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Dashed divider */}
      <div style={{ position: 'relative', width: 22, background: '#0d0a07', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ position: 'absolute', top: -10, left: 3, width: 16, height: 16, borderRadius: '50%', background: 'rgba(30,25,20,0.9)' }} />
        <div style={{ height: '78%', width: 0, borderLeft: '1.5px dashed rgba(255,247,240,0.09)' }} />
        <div style={{ position: 'absolute', bottom: -10, left: 3, width: 16, height: 16, borderRadius: '50%', background: 'rgba(30,25,20,0.9)' }} />
      </div>

      {/* Stub */}
      <div style={{ width: 96, background: '#14110e', padding: '22px 14px', display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <p style={{ fontSize: 6.5, letterSpacing: '0.2em', color: 'rgba(255,247,240,0.26)', textTransform: 'uppercase', marginBottom: 5 }}>seat</p>
          <p style={{ fontSize: 26, fontWeight: 800, color: '#e50d75', lineHeight: 1 }}>A1</p>
        </div>
        <div style={{ textAlign: 'center' }}>
          <p style={{ fontSize: 6.5, letterSpacing: '0.2em', color: 'rgba(255,247,240,0.26)', textTransform: 'uppercase', marginBottom: 4 }}>class</p>
          <p style={{ fontSize: 10, color: 'rgba(255,247,240,0.6)', letterSpacing: '0.06em' }}>FIRST</p>
        </div>
        <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', marginTop: 'auto' }}>
          {BARS.map((h, i) => (
            <div key={i} style={{ width: 2.5, height: h * 4, background: 'rgba(255,247,240,0.4)', borderRadius: 1 }} />
          ))}
        </div>
      </div>
    </div>
  );
}
