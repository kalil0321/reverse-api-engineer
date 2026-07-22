import { NextResponse } from 'next/server';
import { getDocTree, flattenTree } from '@/lib/docs';
import { appName, appTagline, siteUrl, githubUrl, pypiUrl } from '@/lib/shared';

export const dynamic = 'force-static';

export function GET() {
  const pages = flattenTree(getDocTree());

  const docLines = pages
    .map((p) => `- [${p.title}](${new URL(p.url, siteUrl).toString()})`)
    .join('\n');

  const body = `# ${appName}

> ${appTagline}

${appName} is an open-source CLI that captures browser traffic — via browser MCP servers in the default agent mode (or a local Playwright browser with the optional \`[manual]\` extra) — and uses your configured AI SDK to generate a typed API client from the recorded HAR. Output languages: Python, JavaScript, TypeScript, Go, Java, C#, PHP, Ruby, and C.

## Documentation

${docLines}

## Project

- Repository: ${githubUrl}
- PyPI: ${pypiUrl}
- License: MIT
`;

  return new NextResponse(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
