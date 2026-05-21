'use client';

import { useState } from 'react';
import { CopyIcon, CheckIcon } from 'lucide-react';

const COMMAND = 'uv tool install reverse-api-engineer';

export function InstallCommand() {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(COMMAND);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={copy}
      className="inline-flex items-center gap-2 cursor-pointer group"
      aria-label="Copy install command to clipboard"
    >
      <span className="font-mono text-xs text-fd-primary select-none">$</span>
      <code className="font-mono text-xs text-ink-soft tracking-wide select-none group-hover:text-ink transition-colors duration-150">
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
