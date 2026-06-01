import { siClaude, siCursor, siGithubcopilot } from 'simple-icons';

/* Real brand logos for the AI coding agents rae can drive. Logos come from
   simple-icons (monochrome single-path silhouettes rendered at currentColor).
   OpenCode isn't in simple-icons, so it gets a small custom-drawn glyph.

   Canonical agent list mirrors the package's `--sdk` choices:
   Claude Code (default), Cursor, GitHub Copilot, OpenCode. */

type SimpleIcon = { title: string; path: string; hex: string };

export type Agent = {
  key: string;
  name: string;
  note: string;
  href: string;
  hex: string;
  icon?: SimpleIcon;
  custom?: 'opencode';
};

export const AGENTS: Agent[] = [
  {
    key: 'claude',
    name: 'Claude Code',
    note: "Anthropic's coding agent",
    href: 'https://www.anthropic.com/claude-code',
    hex: '#D97757',
    icon: siClaude,
  },
  {
    key: 'cursor',
    name: 'Cursor',
    note: 'The AI code editor',
    href: 'https://cursor.com',
    hex: '#111111',
    icon: siCursor,
  },
  {
    key: 'copilot',
    name: 'GitHub Copilot',
    note: 'Copilot CLI',
    href: 'https://github.com/features/copilot',
    hex: '#111111',
    icon: siGithubcopilot,
  },
  {
    key: 'opencode',
    name: 'OpenCode',
    note: 'Open-source agent',
    href: 'https://opencode.ai',
    hex: '#111111',
    custom: 'opencode',
  },
];

export function BrandIcon({ agent, className }: { agent: Agent; className?: string }) {
  if (agent.custom === 'opencode') {
    // OpenCode isn't in simple-icons, so we use its real mark (from
    // opencode.ai's favicon): a rectangular frame with an inner block.
    // Rendered monochrome at currentColor — the frame is the brand glyph, the
    // inner block sits at reduced opacity so it reads at any size.
    return (
      <svg viewBox="0 0 512 512" className={className} fill="currentColor" aria-hidden="true">
        <title>OpenCode</title>
        <path d="M320 224V352H192V224H320Z" opacity={0.45} />
        <path
          fillRule="evenodd"
          clipRule="evenodd"
          d="M384 416H128V96H384V416ZM320 160H192V352H320V160Z"
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <title>{agent.icon!.title}</title>
      <path d={agent.icon!.path} />
    </svg>
  );
}
