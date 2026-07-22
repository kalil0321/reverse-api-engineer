import type { ReactNode } from 'react';

/* Keep landing content visible in the server-rendered HTML. Entrance motion is
   decorative; images and copy must not depend on hydration or observers. */
export function Reveal({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div data-show="true" className={className}>
      {children}
    </div>
  );
}
