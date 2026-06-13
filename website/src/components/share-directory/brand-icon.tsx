'use client';

import { useState } from 'react';
import { logoUrl } from './clients';

// Brand logo on a clean tile; falls back to the accent monogram tile if the
// logo fails to load (404 / offline). Client component so onError works.
export function BrandIcon({
  domain,
  monogram,
  accent,
  size = 26,
  className = '',
}: {
  domain: string;
  monogram: string;
  accent: string;
  size?: number;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  return (
    <span
      className={`grid place-items-center overflow-hidden shrink-0 ${className}`}
      style={{ background: failed ? accent : '#fff' }}
    >
      {failed ? (
        <span className="text-white font-semibold leading-none" style={{ fontSize: size * 0.46 }}>
          {monogram}
        </span>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={logoUrl(domain)}
          alt=""
          width={size}
          height={size}
          loading="lazy"
          onError={() => setFailed(true)}
          style={{ width: size, height: size, objectFit: 'contain' }}
        />
      )}
    </span>
  );
}
