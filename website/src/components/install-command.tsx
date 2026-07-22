'use client';

import { useState } from 'react';
import { CopyIcon, CheckIcon } from 'lucide-react';

const COMMAND = 'uv tool install reverse-api-engineer';

export function InstallCommand() {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(COMMAND);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard may be unavailable (non-https, denied permission, etc.) */
    }
  };

  return (
    <button
      onClick={copy}
      className="group inline-flex w-full cursor-pointer items-center justify-center gap-1.5 sm:gap-2"
      aria-label="Copy install command to clipboard"
    >
      <span className="font-mono text-xs text-fd-primary select-none">$</span>
      <code className="select-none whitespace-nowrap font-mono text-[10px] tracking-tight text-ink-soft transition-colors duration-150 group-hover:text-ink sm:text-xs sm:tracking-wide">
        {COMMAND}
      </code>
      <span className="flex-shrink-0 w-3">
        {copied
          ? <CheckIcon className="size-3 text-fd-primary" />
          : <CopyIcon className="size-3 text-ink/35 group-hover:text-ink/60 transition-colors duration-150" />
        }
      </span>
    </button>
  );
}
