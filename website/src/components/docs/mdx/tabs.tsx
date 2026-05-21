'use client';

import { useState, Children, isValidElement, useMemo } from 'react';
import type { ReactNode, ReactElement } from 'react';

interface TabsProps {
  items?: string[];
  children: ReactNode;
}

interface TabEntry {
  value: string;
  label: string;
  node: ReactNode;
}

export function Tabs({ items, children }: TabsProps) {
  const tabs = useMemo<TabEntry[]>(() => {
    const out: TabEntry[] = [];
    let idx = 0;
    Children.forEach(children, (child) => {
      if (!isValidElement(child)) return;
      const props = (child as ReactElement<{ value?: string; label?: string }>).props;
      const value = props.value ?? `tab-${idx}`;
      const label = props.label ?? items?.[idx] ?? value;
      out.push({ value, label, node: child });
      idx += 1;
    });
    return out;
  }, [children, items]);

  const [active, setActive] = useState(tabs[0]?.value ?? '');

  if (tabs.length === 0) return null;

  const activeNode = tabs.find((t) => t.value === active)?.node ?? tabs[0].node;

  return (
    <div className="mt-5">
      <div
        role="tablist"
        className="flex items-center gap-5 border-b border-ink/10 overflow-x-auto"
      >
        {tabs.map((t) => {
          const isActive = t.value === active;
          return (
            <button
              key={t.value}
              role="tab"
              type="button"
              aria-selected={isActive}
              onClick={() => setActive(t.value)}
              className={`relative -mb-px py-2 font-mono text-xs whitespace-nowrap transition-colors border-b-2 ${
                isActive
                  ? 'text-ink font-semibold border-fd-primary'
                  : 'text-ink-soft border-transparent hover:text-ink'
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      <div className="mt-3 text-sm leading-relaxed [&>*:first-child]:mt-0">
        {activeNode}
      </div>
    </div>
  );
}

interface TabProps {
  value?: string;
  label?: string;
  children: ReactNode;
}

export function Tab({ children }: TabProps) {
  return <>{children}</>;
}
