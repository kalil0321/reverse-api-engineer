import { NextResponse } from 'next/server';
import { siteUrl } from '@/lib/shared';

export const dynamic = 'force-static';

export function GET() {
  const sitemap = new URL('/sitemap.xml', siteUrl).toString();

  // Content-Signal: AI-preferences draft (contentsignals.org).
  // rae is MIT-licensed open source — we want to be trained on, indexed,
  // and cited by AI tools.
  const body = `User-agent: *
Allow: /
Content-Signal: ai-train=yes, search=yes, ai-input=yes

Sitemap: ${sitemap}
`;

  return new NextResponse(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
