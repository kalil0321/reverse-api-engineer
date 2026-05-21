import Link from 'next/link';
import type { ReactNode } from 'react';
import { ArrowRightIcon } from 'lucide-react';

export function Cards({ children }: { children: ReactNode }) {
  return (
    <div className="mt-5 grid grid-cols-1 min-[480px]:grid-cols-2 gap-3">
      {children}
    </div>
  );
}

interface CardProps {
  title: ReactNode;
  description?: ReactNode;
  href?: string;
  icon?: ReactNode;
}

export function Card({ title, description, href, icon }: CardProps) {
  const inner = (
    <div className="docs-card group/card h-full rounded-2xl p-6">
      <div className="flex items-center gap-2.5 text-ink">
        {icon ? (
          <span className="inline-flex items-center justify-center size-6 text-fd-primary">
            {icon}
          </span>
        ) : null}
        <span className="font-display text-lg tracking-tight">{title}</span>
        {href ? (
          <ArrowRightIcon className="ml-auto size-4 text-ink-soft transition-transform duration-200 group-hover/card:translate-x-1 group-hover/card:text-fd-primary" />
        ) : null}
      </div>
      {description ? (
        <p className="mt-2.5 text-sm text-ink-soft leading-relaxed">{description}</p>
      ) : null}
    </div>
  );

  if (!href) return inner;

  return (
    <Link
      href={href}
      className="block no-underline text-ink hover:text-ink [&_*]:text-inherit"
      style={{ textDecoration: 'none', color: 'inherit' }}
    >
      {inner}
    </Link>
  );
}
