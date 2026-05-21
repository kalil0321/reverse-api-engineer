'use client';

import { useRef, useState, type ReactNode } from 'react';
import { CopyIcon, CheckIcon } from 'lucide-react';

interface CodeBlockProps {
  children?: ReactNode;
}

export function CodeBlock({ children }: CodeBlockProps) {
  const ref = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    const text = ref.current?.textContent ?? '';
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be unavailable */
    }
  };

  return (
    <div className="group/codeblock relative">
      <pre
        ref={ref}
        className="overflow-x-auto rounded-xl px-6 py-5 font-mono text-[0.82rem] leading-[1.7] text-ink"
        style={{
          backgroundColor: 'color-mix(in oklch, var(--color-ink) 8%, transparent)',
        }}
      >
        {children}
      </pre>
      <button
        type="button"
        onClick={onCopy}
        aria-label="Copy code"
        className="absolute top-2.5 right-2.5 inline-flex items-center gap-1 px-2 py-1 rounded-md text-ink-soft hover:text-ink font-mono text-[0.7rem] opacity-0 group-hover/codeblock:opacity-100 transition-opacity"
        style={{
          backgroundColor: 'color-mix(in oklch, var(--color-ink) 8%, transparent)',
        }}
      >
        {copied ? (
          <>
            <CheckIcon className="size-3 text-fd-primary" />
            copied
          </>
        ) : (
          <>
            <CopyIcon className="size-3" />
            copy
          </>
        )}
      </button>
    </div>
  );
}

export function InlineCode({ children }: { children: ReactNode }) {
  return (
    <code className="font-mono text-[0.88em] bg-ink/[0.06] text-ink px-1.5 py-0.5 rounded">
      {children}
    </code>
  );
}
