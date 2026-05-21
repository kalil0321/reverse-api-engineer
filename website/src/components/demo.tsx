interface DemoProps {
  src: string;
  alt: string;
  caption?: string;
}

/**
 * Inline media (GIF / screenshot) inside MDX docs.
 * Image in a clean rounded frame, caption italic + centred + separated
 * by a small margin below the image.
 */
export function Demo({ src, alt, caption }: DemoProps) {
  return (
    <figure className="not-prose mt-5 flex flex-col items-center">
      <div className="w-full overflow-hidden rounded-xl border border-ink/10 bg-cream-soft">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} loading="lazy" className="block w-full h-auto" />
      </div>
      {caption ? (
        <figcaption className="mt-4 text-sm italic text-ink-soft text-center max-w-prose">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}
