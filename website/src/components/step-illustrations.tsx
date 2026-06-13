import type { ReactNode } from 'react';

/* Spot illustrations for the four "how it works" steps, used as the photos
   inside the polaroid frames. Colors are FIXED (not theme tokens) because a
   printed photo looks the same under any lighting — only the wall behind it
   (the section background) themes. Subtle motion comes from the `ill-*`
   classes in global.css (reduced-motion safe). */

const INK = '#241c14';
const CARD = '#fffdf8';
const PINK = '#e50d75';
const ACCENT = '#ffe1eb';

function Ink({ children, w = 1.6 }: { children: ReactNode; w?: number }) {
  return (
    <g fill="none" stroke={INK} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round">
      {children}
    </g>
  );
}

function Aster({ x, y, size = 22, className }: { x: number; y: number; size?: number; className?: string }) {
  return (
    <text x={x} y={y} className={className} fontFamily="var(--font-display)" fontStyle="italic" fontSize={size} fill={PINK} textAnchor="middle">
      *
    </text>
  );
}

export function StepBrowse() {
  return (
    <svg viewBox="0 0 180 160" className="h-auto w-full" role="img" aria-label="Browse">
      <rect x="22" y="26" width="136" height="98" rx="10" fill={CARD} stroke={INK} strokeWidth={1.6} />
      <Ink>
        <line x1="22" y1="46" x2="158" y2="46" />
        <line x1="40" y1="64" x2="96" y2="64" opacity={0.4} />
        <line x1="40" y1="78" x2="128" y2="78" opacity={0.4} />
        <line x1="40" y1="92" x2="110" y2="92" opacity={0.4} />
      </Ink>
      <circle cx="34" cy="36" r="3" fill={PINK} />
      <path className="ill-cursor" d="M104 96 L104 132 L114 122 L121 138 L127 135 L120 120 L134 120 Z" fill={CARD} stroke={INK} strokeWidth={1.6} strokeLinejoin="round" />
    </svg>
  );
}

export function StepCapture() {
  return (
    <svg viewBox="0 0 180 160" className="h-auto w-full" role="img" aria-label="Capture">
      <rect x="34" y="20" width="112" height="120" rx="10" fill={CARD} stroke={INK} strokeWidth={1.6} />
      <circle cx="124" cy="40" r="6" fill={PINK} />
      <text x="46" y="44" fontFamily="var(--font-mono)" fontSize="11" fill={INK} opacity={0.55}>.har</text>
      <Ink w={1.5}>
        <line x1="50" y1="64" x2="60" y2="64" stroke={PINK} />
        <line x1="66" y1="64" x2="130" y2="64" opacity={0.45} />
        <line x1="50" y1="80" x2="60" y2="80" stroke={PINK} />
        <line x1="66" y1="80" x2="118" y2="80" opacity={0.45} />
        <line x1="50" y1="96" x2="60" y2="96" stroke={PINK} />
        <line x1="66" y1="96" x2="126" y2="96" opacity={0.45} />
        <polyline className="ill-wave" points="50,118 60,118 64,108 70,128 76,112 82,122 88,118 130,118" opacity={0.7} />
      </Ink>
    </svg>
  );
}

export function StepGenerate() {
  return (
    <svg viewBox="0 0 180 160" className="h-auto w-full" role="img" aria-label="Generate">
      <path d="M44 24 H118 L140 46 V138 H44 Z" fill={CARD} stroke={INK} strokeWidth={1.6} strokeLinejoin="round" />
      <path d="M118 24 V46 H140" fill="none" stroke={INK} strokeWidth={1.6} strokeLinejoin="round" />
      {/* code lines write themselves in sequence */}
      <Ink w={1.5}>
        <line className="ill-write" style={{ animationDelay: '0s' }} x1="58" y1="74" x2="74" y2="74" stroke={PINK} />
        <line className="ill-write" style={{ animationDelay: '0.1s' }} x1="80" y1="74" x2="122" y2="74" opacity={0.45} />
        <line className="ill-write" style={{ animationDelay: '0.45s' }} x1="68" y1="88" x2="112" y2="88" opacity={0.45} />
        <line className="ill-write" style={{ animationDelay: '0.8s' }} x1="68" y1="102" x2="100" y2="102" stroke={PINK} />
        <line className="ill-write" style={{ animationDelay: '1.15s' }} x1="58" y1="116" x2="92" y2="116" opacity={0.45} />
      </Ink>
      {/* static output spark */}
      <Aster x={140} y={36} size={22} />
      <Ink w={1.5}>
        <line x1="150" y1="14" x2="154" y2="8" stroke={PINK} />
        <line x1="160" y1="24" x2="168" y2="22" stroke={PINK} />
      </Ink>
    </svg>
  );
}

export function StepReview() {
  return (
    <svg viewBox="0 0 180 160" className="h-auto w-full" role="img" aria-label="Review">
      <path d="M40 24 H110 L132 46 V138 H40 Z" fill={CARD} stroke={INK} strokeWidth={1.6} strokeLinejoin="round" />
      <path d="M110 24 V46 H132" fill="none" stroke={INK} strokeWidth={1.6} strokeLinejoin="round" />
      <Ink w={1.5}>
        <line x1="54" y1="66" x2="116" y2="66" opacity={0.4} />
        <line x1="54" y1="80" x2="100" y2="80" opacity={0.4} />
        <line x1="54" y1="94" x2="110" y2="94" opacity={0.4} />
      </Ink>
      <g className="ill-mag">
        <circle cx="104" cy="104" r="22" fill={ACCENT} stroke={INK} strokeWidth={1.6} />
        <line x1="120" y1="120" x2="140" y2="140" stroke={INK} strokeWidth={2.2} strokeLinecap="round" />
        <polyline className="ill-check" points="94,104 101,112 116,96" fill="none" stroke={PINK} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}
