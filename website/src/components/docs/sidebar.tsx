'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRightIcon } from 'lucide-react';
import { useState, useMemo } from 'react';
import type { TreeNode } from '@/lib/docs';

export function DocsSidebar({ tree }: { tree: TreeNode[] }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Documentation">
      <ul className="flex flex-col gap-0.5 text-sm">
        {tree.map((node, i) => (
          <Render key={i} node={node} pathname={pathname} depth={0} />
        ))}
      </ul>
    </nav>
  );
}

function Render({ node, pathname, depth }: { node: TreeNode; pathname: string; depth: number }) {
  if (node.type === 'separator') {
    return (
      <li
        className={`font-mono text-[0.65rem] uppercase tracking-[0.18em] text-ink-soft px-3 ${
          depth === 0 ? 'mt-6 mb-1' : 'mt-3 mb-1'
        }`}
      >
        {node.title}
      </li>
    );
  }

  if (node.type === 'folder') {
    return <FolderItem node={node} pathname={pathname} depth={depth} />;
  }

  return <PageItem url={node.url} title={node.title} pathname={pathname} depth={depth} />;
}

function FolderItem({
  node,
  pathname,
  depth,
}: {
  node: Extract<TreeNode, { type: 'folder' }>;
  pathname: string;
  depth: number;
}) {
  const containsActive = useMemo(() => folderContainsActive(node, pathname), [node, pathname]);
  const [open, setOpen] = useState(containsActive || depth === 0);

  return (
    <li className="flex flex-col">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-between w-full text-left px-3 py-1.5 rounded-md text-ink-soft hover:text-ink hover:bg-ink/[0.04] transition-colors"
      >
        <span className="font-medium">{node.title}</span>
        <ChevronRightIcon
          className={`size-3.5 text-ink-soft transition-transform ${open ? 'rotate-90' : ''}`}
        />
      </button>
      {open && (
        <ul className="flex flex-col gap-0.5 mt-0.5 ml-3 pl-3 border-l border-ink/10">
          {node.children.map((child, i) => (
            <Render key={i} node={child} pathname={pathname} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

function PageItem({
  url,
  title,
  pathname,
  depth,
}: {
  url: string;
  title: string;
  pathname: string;
  depth: number;
}) {
  const normalized = pathname.replace(/\/$/, '');
  const isActive = normalized === url || normalized === `${url}/`;
  return (
    <li>
      <Link
        href={url}
        className={`block py-1.5 px-3 rounded-md transition-colors ${
          isActive
            ? 'bg-fd-accent text-fd-primary font-medium'
            : 'text-ink-soft hover:text-ink hover:bg-ink/[0.04]'
        } ${depth > 0 ? '' : ''}`}
      >
        {title}
      </Link>
    </li>
  );
}

function folderContainsActive(
  node: Extract<TreeNode, { type: 'folder' }>,
  pathname: string,
): boolean {
  const p = pathname.replace(/\/$/, '');
  for (const child of node.children) {
    if (child.type === 'page' && (p === child.url || p === `${child.url}/`)) return true;
    if (child.type === 'folder' && folderContainsActive(child, pathname)) return true;
  }
  return false;
}
