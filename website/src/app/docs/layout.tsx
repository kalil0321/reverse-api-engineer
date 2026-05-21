import { getDocTree } from '@/lib/docs';
import { SiteNav } from '@/components/site-nav';
import { DocsSidebar } from '@/components/docs/sidebar';

export default function Layout({ children }: { children: React.ReactNode }) {
  const tree = getDocTree();

  return (
    <>
      <SiteNav />

      {/* Fixed sidebar — true viewport vertical centring, left edge
          aligned with the docs container's content edge. Stays fully
          visible while scrolling. */}
      <aside className="docs-sidebar-fixed">
        <nav
          className="w-full max-h-full overflow-y-auto pr-3"
          style={{ pointerEvents: 'auto' }}
        >
          <DocsSidebar tree={tree} />
        </nav>
      </aside>

      <div className="mx-auto max-w-7xl px-6 lg:px-10 w-full">
        <div
          className="grid gap-12 lg:gap-16"
          style={{ gridTemplateColumns: '240px minmax(0, 1fr)' }}
        >
          {/* Placeholder — preserves the main content's horizontal position
              now that the sidebar is fixed (out of flow). */}
          <div aria-hidden />
          <main className="min-w-0 pt-6 pb-16 md:pt-8">{children}</main>
        </div>
      </div>
    </>
  );
}
