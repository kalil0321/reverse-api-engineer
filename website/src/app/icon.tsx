import { ImageResponse } from 'next/og';

export const size = { width: 64, height: 64 };
export const contentType = 'image/png';
export const dynamic = 'force-static';
export const revalidate = false;

/**
 * Loads only the glyphs needed (the asterisk) from Google Fonts.
 * Runs at build time during static export.
 */
async function loadFrauncesItalic(text: string): Promise<ArrayBuffer> {
  const url = `https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@1,144,500&text=${encodeURIComponent(
    text,
  )}&display=swap`;
  const css = await (await fetch(url)).text();
  const resource = css.match(/src:\s*url\(([^)]+)\)\s*format\('(?:opentype|truetype|woff2?)'\)/);
  if (!resource) throw new Error('Could not locate Fraunces font URL in CSS response');
  const fontResponse = await fetch(resource[1]);
  if (!fontResponse.ok) throw new Error(`Font fetch failed: ${fontResponse.status}`);
  return fontResponse.arrayBuffer();
}

export default async function Icon() {
  const fontData = await loadFrauncesItalic('*');

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          background: 'transparent',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            fontFamily: 'Fraunces',
            fontStyle: 'italic',
            fontWeight: 500,
            fontSize: 96,
            color: '#e50d75',
            lineHeight: 1,
            // Optical centering: Fraunces asterisk sits high in its em-box
            transform: 'translateY(8px) rotate(-6deg)',
            display: 'flex',
          }}
        >
          *
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        {
          name: 'Fraunces',
          data: fontData,
          style: 'italic',
          weight: 500,
        },
      ],
    },
  );
}
