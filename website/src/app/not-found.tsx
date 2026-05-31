import Link from 'next/link';
import { ArrowRightIcon } from 'lucide-react';
import { SiteNav } from '@/components/site-nav';

export default function NotFound() {
  return (
    <div className="relative flex flex-1 flex-col bg-color-mesh">
      <SiteNav />
      <main className="flex-1 flex">
        <section className="relative overflow-hidden flex-1 flex items-center">
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

          <div className="relative mx-auto max-w-7xl px-6 lg:px-10 py-24">
            <div className="mx-auto max-w-3xl text-center">
              <h1 className="hero-display">
                Page not<br />
                <em>found.</em>
              </h1>

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
    </div>
  );
}
