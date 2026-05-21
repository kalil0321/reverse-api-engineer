'use client';

import Link from 'next/link';
import { ArrowRightIcon, RotateCcwIcon } from 'lucide-react';
import { SiteNav } from '@/components/site-nav';
import { SiteFooter } from '@/components/site-footer';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <>
      <SiteNav />
      <main className="flex-1">
        <section className="relative overflow-hidden bg-cream">
          <span
            aria-hidden="true"
            className="absolute top-10 right-10 hidden md:block font-display italic text-6xl text-fd-primary/30 select-none -rotate-12"
          >
            *
          </span>

          <div className="relative mx-auto max-w-7xl px-6 lg:px-10 pt-24 md:pt-36 pb-24 md:pb-32">
            <div className="mx-auto max-w-3xl">
              <span className="eyebrow text-ink-soft">Something went wrong</span>

              <h1 className="hero-display mt-8">
                Unexpected<br />
                <em>error.</em>
              </h1>

              <p className="mt-8 text-base md:text-lg text-ink-soft max-w-md leading-relaxed">
                An error occurred while rendering this page. You can try again
                or go back home.
              </p>

              {error.message && (
                <div className="mt-8 max-w-xl terminal-window">
                  <div className="terminal-window-bar">
                    <span className="terminal-dot" />
                    <span className="terminal-dot" />
                    <span className="terminal-dot" />
                    <span className="ml-3 font-mono text-xs text-ink-soft">error</span>
                  </div>
                  <div className="terminal-window-body text-[0.8125rem]">
                    <p>
                      <span className="text-fd-primary">!</span>{' '}
                      <span className="text-ink">{error.message}</span>
                    </p>
                    {error.digest && (
                      <p className="mt-1 text-ink-soft">
                        digest: <span className="text-ink">{error.digest}</span>
                      </p>
                    )}
                  </div>
                </div>
              )}

              <div className="mt-10 inline-flex flex-wrap items-center gap-3">
                <button onClick={reset} className="btn-primary">
                  <RotateCcwIcon className="size-4" />
                  Try again
                </button>
                <Link href="/" className="btn-secondary">
                  Back to home
                  <ArrowRightIcon className="size-4" />
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
