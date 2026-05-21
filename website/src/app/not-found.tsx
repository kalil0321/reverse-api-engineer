import Link from 'next/link';
import { ArrowRightIcon } from 'lucide-react';
import { SiteNav } from '@/components/site-nav';
import { SiteFooter } from '@/components/site-footer';

export default function NotFound() {
  return (
    <>
      <SiteNav />
      <main className="flex-1">
        <section className="relative overflow-hidden bg-color-mesh">
          <span
            aria-hidden="true"
            className="absolute top-10 right-10 hidden md:block font-display italic text-6xl text-fd-primary/45 select-none -rotate-12"
          >
            *
          </span>
          <span
            aria-hidden="true"
            className="absolute bottom-20 left-10 hidden md:block font-display italic text-4xl text-ink/20 select-none rotate-12"
          >
            *
          </span>

          <div className="relative mx-auto max-w-7xl px-6 lg:px-10 pt-24 md:pt-36 pb-24 md:pb-32">
            <div className="mx-auto max-w-3xl text-center">
              <span className="eyebrow text-ink-soft">Error 404</span>

              <h1 className="hero-display mt-8">
                Page not<br />
                <em>found.</em>
              </h1>

              <p className="mt-8 text-base md:text-lg text-ink-soft max-w-md mx-auto leading-relaxed">
                The URL you requested doesn't exist — it may have moved or never
                existed. Check the address, or head back home.
              </p>

              <div className="mt-10 inline-flex flex-wrap items-center justify-center gap-3">
                <Link href="/" className="btn-primary">
                  Back to home
                  <ArrowRightIcon className="size-4" />
                </Link>
                <Link href="/docs" className="btn-secondary">
                  Read the docs
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
