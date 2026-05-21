import type { MDXComponents } from 'mdx/types';
import type { ComponentProps, ReactNode } from 'react';
import Link from 'next/link';
import { Callout } from './mdx/callout';
import { Tabs, Tab } from './mdx/tabs';
import { Steps, Step } from './mdx/steps';
import { Files, Folder, File } from './mdx/files';
import { Cards, Card } from './mdx/cards';
import { CodeBlock } from './mdx/code-block';
import { Demo } from '../demo';

/* ─── Inline link ──────────────────────────────────────────────────────── */

const linkClass =
  'text-fd-primary underline decoration-fd-primary/45 decoration-1 underline-offset-[3px] ' +
  'rounded px-1 -mx-1 transition-colors hover:bg-fd-primary/[0.18]';

function AnchorLink({ href, children, ...rest }: ComponentProps<'a'> & { href?: string }) {
  const isExternal = href?.startsWith('http') || href?.startsWith('//');
  if (isExternal) {
    return (
      <a {...rest} href={href} target="_blank" rel="noopener noreferrer" className={linkClass}>
        {children}
      </a>
    );
  }
  return (
    <Link href={href ?? '#'} className={linkClass}>
      {children}
    </Link>
  );
}

/* ─── Inline code ──────────────────────────────────────────────────────── */

function InlineCode({ children }: { children: ReactNode }) {
  return (
    <code className="font-mono text-[0.88em] bg-ink/[0.07] text-ink px-1.5 py-0.5 rounded">
      {children}
    </code>
  );
}

/* ─── MDX components map ──────────────────────────────────────────────────
   Every HTML element gets its className right here. No external CSS prose
   to override or conflict with. Spacing uses only `mt-*` (works cleanly
   with flex-col parents AND regular block flow because margin-collapsing
   picks the larger value naturally). */

export function getDocsMdxComponents(extra?: MDXComponents): MDXComponents {
  return {
    /* Headings — `mt-*` only. The next element's own `mt-*` provides the
       gap below the heading. Keeps spacing predictable under flex-col. */
    h2: (props) => (
      <h2
        className="font-display text-3xl tracking-[-0.035em] text-ink mt-10 leading-tight scroll-mt-24"
        {...props}
      />
    ),
    h3: (props) => (
      <h3
        className="font-display text-xl tracking-tight text-ink mt-8 leading-tight scroll-mt-24"
        {...props}
      />
    ),
    h4: (props) => (
      <h4
        className="font-display text-lg font-semibold tracking-tight text-ink mt-6 scroll-mt-24"
        {...props}
      />
    ),

    /* Text flow */
    p: (props) => <p className="mt-5 leading-relaxed text-ink/85" {...props} />,
    strong: (props) => <strong className="font-semibold text-ink" {...props} />,
    em: (props) => <em className="italic" {...props} />,
    a: AnchorLink,

    /* Lists — list-style + bullet color handled in global.css `.mdx ul/ol`
       because Tailwind v4 doesn't reliably compile `list-disc` / `marker:*`. */
    ul: (props) => <ul className="mt-5 text-ink/85" {...props} />,
    ol: (props) => <ol className="mt-5 text-ink/85" {...props} />,
    li: (props) => <li className="leading-relaxed" {...props} />,

    /* Quote */
    blockquote: (props) => (
      <blockquote
        className="mt-5 border-l-2 border-fd-primary pl-4 font-display italic text-ink/80"
        {...props}
      />
    ),

    /* HR */
    hr: () => <hr className="mt-10 mb-0 border-0 border-t border-ink/10" />,

    /* Images (Demo handles its own framing) */
    img: (props: ComponentProps<'img'>) => (
      // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
      <img className="mt-5 rounded-xl border border-ink/10" {...props} />
    ),

    /* Code (inline vs block) */
    pre: CodeBlock,
    code: ({ children, ...rest }: ComponentProps<'code'>) => {
      // Inline code: plain string children. Block code: tree of <span>s.
      if (typeof children === 'string') return <InlineCode>{children}</InlineCode>;
      return <code {...rest}>{children}</code>;
    },

    /* Tables — wrap in overflow-x container; cells use .docs-table CSS */
    table: (props) => (
      <div className="mt-5 overflow-x-auto rounded-xl border border-ink/10">
        <table {...props} className="docs-table" />
      </div>
    ),

    /* Custom MDX block components */
    Callout,
    Tabs,
    Tab,
    Steps,
    Step,
    Files,
    Folder,
    File,
    Cards,
    Card,
    Demo,

    ...extra,
  } satisfies MDXComponents;
}

export const getMDXComponents = getDocsMdxComponents;
