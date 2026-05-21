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

export interface TocItem {
  title: string;
  url: string;     // "#some-slug"
  depth: number;   // 2..4
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
      return {
        slug: segments,
        url: segments.length === 0 ? BASE_URL : `${BASE_URL}/${segments.join('/')}`,
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
          url,
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
        url: `${BASE_URL}/${slug.join('/')}`,
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
    if (n.type === 'page') out.push({ url: n.url, title: n.title });
    if (n.type === 'folder') out.push(...flattenTree(n.children));
  }
  return out;
}

// ─── TOC extraction (regex-based, matches rehype-slug) ────────────────────

export function extractToc(mdx: string): TocItem[] {
  const out: TocItem[] = [];
  let inFence = false;
  for (const line of mdx.split('\n')) {
    if (line.startsWith('```')) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const m = line.match(/^(#{2,4})\s+(.+?)\s*$/);
    if (m) {
      const depth = m[1].length;
      const title = m[2].replace(/[*_`]/g, '');
      const slug = slugify(title);
      out.push({ title, url: `#${slug}`, depth });
    }
  }
  return out;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
}
