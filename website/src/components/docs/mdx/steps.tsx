import type { ReactNode } from 'react';

export function Steps({ children }: { children: ReactNode }) {
  return <ol className="mt-5 flex flex-col gap-3">{children}</ol>;
}

export function Step({ children }: { children: ReactNode }) {
  return (
    <li>
      <div className="[&>*:first-child]:mt-0">{children}</div>
    </li>
  );
}
