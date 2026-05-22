import { ChevronDownIcon } from 'lucide-react';
import { getDocTree } from '@/lib/docs';
import { SiteNav } from '@/components/site-nav';
import { DocsSidebar } from '@/components/docs/sidebar';

export default function Layout({ children }: { children: React.ReactNode }) {
  const tree = getDocTree();

  return (
    <>
      <SiteNav />

      {/* lg+ : fixed sidebar, vertically centred against the viewport, left
          edge aligned with the docs container.  < lg: hidden via CSS — the
          mobile <details> menu below takes over. */}
      <aside className="docs-sidebar-fixed">
        <div
          className="h-full overflow-y-auto"
          style={{ pointerEvents: 'auto' }}
        >
          {/* `safe center` falls back to `flex-start` when the nav overflows,
              so the scrollbar stays usable instead of pushing content off the
              top of the scroll container. */}
          <nav className="min-h-full flex flex-col [justify-content:safe_center] px-3 py-2">
            <DocsSidebar tree={tree} />
          </nav>
        </div>
      </aside>

      <div className="mx-auto max-w-7xl px-6 lg:px-10 w-full">
        {/* Mobile docs menu — collapsible, no JS needed. Hidden on lg+. */}
        <details className="lg:hidden mt-4 mx-auto max-w-[740px] group rounded-xl border border-ink/10">
          <summary className="flex items-center justify-between px-4 py-3 cursor-pointer list-none font-mono text-xs uppercase tracking-widest text-ink-soft">
            <span>Documentation</span>
            <ChevronDownIcon className="size-4 transition-transform group-open:rotate-180" />
          </summary>
          <div className="px-3 pb-3 pt-1 border-t border-ink/10 max-h-[60vh] overflow-y-auto">
            <DocsSidebar tree={tree} />
          </div>
        </details>

        <div className="lg:grid lg:gap-8 xl:gap-0 lg:[grid-template-columns:240px_minmax(0,1fr)]">
          {/* Placeholder — preserves main's horizontal position next to the
              fixed sidebar on lg+. Hidden under lg. */}
          <div aria-hidden className="hidden lg:block" />
          <main className="min-w-0 pt-6 pb-4 md:pt-8">{children}</main>
        </div>
      </div>
    </>
  );
}
