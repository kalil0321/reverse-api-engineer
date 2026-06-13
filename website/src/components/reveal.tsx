'use client';

import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

/* Flips data-show to "true" the first time it scrolls into view, so CSS
   entrance animations (e.g. the polaroid rise, the sticky-note drop) play on
   entry rather than on load. Reduced-motion is handled in the CSS. */
export function Reveal({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [show, setShow] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      setShow(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setShow(true);
            io.disconnect();
            break;
          }
        }
      },
      { threshold: 0.2 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={ref} data-show={show ? 'true' : 'false'} className={className}>
      {children}
    </div>
  );
}
