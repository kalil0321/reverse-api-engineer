import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';

const DOCS_DIR = path.join(process.cwd(), 'content', 'docs');
const BASE_URL = '/docs';

// ─── Types ────────────────────────────────────────────────────────────────

export interface DocFrontmatter {
  title: string;
  description?: string;
}

export interface DocPage {
  slug: string[];             // [], ['installation'], ['modes', 'agent']
  url: string;                // /docs, /docs/installation, /docs/modes/agent
  filePath: string;           // absolute fs path
  frontmatter: DocFrontmatter;
  content: string;            // raw MDX body (no frontmatter)
}

export type TreeNode =
  | { type: 'page'; url: string; title: string }
  | { type: 'folder'; title: string; children: TreeNode[] }
  | { type: 'separator'; title: string };

// ─── Helpers ──────────────────────────────────────────────────────────────

function readMeta(dir: string): { pages?: string[]; title?: string } | null {
  const p = path.join(dir, 'meta.json');
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function titleCase(s: string): string {
  return s.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function isSeparator(name: string): string | null {
  const m = name.match(/^-{3}(.+?)-{3}$/);
  return m ? m[1] : null;
}

/* Sanitise a docs URL to a relative path under /docs/. Filenames come from
   the local filesystem and are inherently safe, but this guard satisfies
   static analysers that taint-track every fs-derived string. */
function safeDocsUrl(url: string): string {
  return /^\/docs(\/[A-Za-z0-9\-_/]*)?$/.test(url) ? url : BASE_URL;
}

// ─── Page loader ──────────────────────────────────────────────────────────

export function getDocPage(slug: string[] | undefined): DocPage | null {
  const segments = slug ?? [];
  const candidates: string[] = [];

  if (segments.length === 0) {
    candidates.push(path.join(DOCS_DIR, 'index.mdx'));
  } else {
    candidates.push(path.join(DOCS_DIR, ...segments) + '.mdx');
    candidates.push(path.join(DOCS_DIR, ...segments, 'index.mdx'));
  }

  for (const filePath of candidates) {
    if (fs.existsSync(filePath)) {
      const raw = fs.readFileSync(filePath, 'utf8');
      const parsed = matter(raw);
      const url = segments.length === 0 ? BASE_URL : `${BASE_URL}/${segments.join('/')}`;
      return {
        slug: segments,
        url: safeDocsUrl(url),
        filePath,
        frontmatter: parsed.data as DocFrontmatter,
        content: parsed.content,
      };
    }
  }
  return null;
}

// ─── All pages (for static params) ────────────────────────────────────────

export function getAllDocPages(): DocPage[] {
  const out: DocPage[] = [];
  walk(DOCS_DIR, []);
  return out;

  function walk(dir: string, segments: string[]) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name === 'meta.json') continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full, [...segments, entry.name]);
      } else if (entry.name.endsWith('.mdx')) {
        const base = entry.name.replace(/\.mdx$/, '');
        const slug = base === 'index' ? segments : [...segments, base];
        const page = getDocPage(slug);
        if (page) out.push(page);
      }
    }
  }
}

// ─── Sidebar tree ─────────────────────────────────────────────────────────

export function getDocTree(): TreeNode[] {
  return buildTree(DOCS_DIR, []);
}

function buildTree(dir: string, segments: string[]): TreeNode[] {
  const meta = readMeta(dir);
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  const childEntries = entries
    .filter((e) => e.name !== 'meta.json' && (e.isDirectory() || e.name.endsWith('.mdx')))
    .map((e) => (e.isDirectory() ? e.name : e.name.replace(/\.mdx$/, '')));

  const order: string[] = meta?.pages
    ? meta.pages
    : childEntries.filter((n) => n !== 'index');

  const tree: TreeNode[] = [];

  for (const item of order) {
    const sep = isSeparator(item);
    if (sep) {
      tree.push({ type: 'separator', title: sep.trim() });
      continue;
    }

    if (item === 'index') {
      // Render the folder's own index.mdx as a top-level link
      const indexPath = path.join(dir, 'index.mdx');
      if (fs.existsSync(indexPath)) {
        const fm = matter(fs.readFileSync(indexPath, 'utf8')).data as DocFrontmatter;
        const url = segments.length === 0 ? BASE_URL : `${BASE_URL}/${segments.join('/')}`;
        tree.push({
          type: 'page',
          url: safeDocsUrl(url),
          title: fm.title ?? 'Introduction',
        });
      }
      continue;
    }

    const mdxPath = path.join(dir, `${item}.mdx`);
    const folderPath = path.join(dir, item);

    if (fs.existsSync(folderPath) && fs.statSync(folderPath).isDirectory()) {
      const childTree = buildTree(folderPath, [...segments, item]);
      const folderMeta = readMeta(folderPath);
      tree.push({
        type: 'folder',
        title: folderMeta?.title ?? titleCase(item),
        children: childTree,
      });
    } else if (fs.existsSync(mdxPath)) {
      const raw = fs.readFileSync(mdxPath, 'utf8');
      const fm = matter(raw).data as DocFrontmatter;
      const slug = [...segments, item];
      tree.push({
        type: 'page',
        url: safeDocsUrl(`${BASE_URL}/${slug.join('/')}`),
        title: fm.title ?? titleCase(item),
      });
    }
  }

  return tree;
}

// ─── Flatten tree for prev/next nav ───────────────────────────────────────

export function flattenTree(nodes: TreeNode[]): Array<{ url: string; title: string }> {
  const out: Array<{ url: string; title: string }> = [];
  for (const n of nodes) {
    if (n.type === 'page') out.push({ url: safeDocsUrl(n.url), title: n.title });
    if (n.type === 'folder') out.push(...flattenTree(n.children));
  }
  return out;
}

