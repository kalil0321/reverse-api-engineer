import fs from 'node:fs';
import type { MetadataRoute } from 'next';
import { getAllDocPages } from '@/lib/docs';
import { siteUrl } from '@/lib/shared';

export const dynamic = 'force-static';

function absoluteUrl(path: string) {
  return new URL(path, siteUrl).toString();
}

function lastModified(filePath?: string) {
  if (!filePath) return new Date();
  try {
    return fs.statSync(filePath).mtime;
  } catch {
    return new Date();
  }
}

export default function sitemap(): MetadataRoute.Sitemap {
  const docs = getAllDocPages().map((page) => ({
    url: absoluteUrl(page.url),
    lastModified: lastModified(page.filePath),
    changeFrequency: 'weekly' as const,
    priority: page.url === '/docs' ? 0.8 : 0.65,
  }));

  return [
    {
      url: absoluteUrl('/'),
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 1,
    },
    ...docs,
  ];
}
