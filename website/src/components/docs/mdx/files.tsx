import type { ReactNode } from 'react';
import { FolderIcon, FileIcon as LucideFileIcon } from 'lucide-react';

export function Files({ children }: { children: ReactNode }) {
  return (
    <div className="mt-5 rounded-xl border border-ink/10 bg-cream-soft p-4 font-mono text-sm">
      <ul className="docs-files-list flex flex-col gap-1">{children}</ul>
    </div>
  );
}

interface FolderProps {
  name: string;
  defaultOpen?: boolean;
  children?: ReactNode;
}

export function Folder({ name, children }: FolderProps) {
  return (
    <li>
      <div className="flex items-center gap-2 text-ink">
        <FolderIcon className="size-3.5 text-fd-primary" aria-hidden="true" />
        <span className="font-medium">{name}</span>
      </div>
      {children ? (
        <ul className="docs-files-list flex flex-col gap-1 mt-1 ml-2 pl-3 border-l border-ink/10">
          {children}
        </ul>
      ) : null}
    </li>
  );
}

export function File({ name }: { name: string }) {
  return (
    <li className="flex items-center gap-2 text-ink-soft">
      <LucideFileIcon className="size-3.5 text-ink-soft/70" aria-hidden="true" />
      <span>{name}</span>
    </li>
  );
}
