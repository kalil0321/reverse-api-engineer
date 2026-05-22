import './global.css';
import { Inter, JetBrains_Mono, Fraunces } from 'next/font/google';
import type { Metadata } from 'next';
import { appName, appTagline, gitConfig, siteUrl } from '@/lib/shared';
import { Providers } from '@/components/providers';

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  applicationName: appName,
  title: {
    default: `${appName} · Turn websites into APIs`,
    template: `%s · ${appName}`,
  },
  description: appTagline,
  keywords: [
    'API reverse engineering',
    'HAR capture',
    'API client generator',
    'browser traffic API',
    'typed API client',
  ],
  alternates: {
    canonical: '/',
  },
  openGraph: {
    type: 'website',
    siteName: appName,
    title: `${appName} · Turn websites into APIs`,
    description: appTagline,
    url: '/',
    images: [
      {
        url: `https://raw.githubusercontent.com/${gitConfig.user}/${gitConfig.repo}/main/assets/reverse-api-banner.jpg`,
        width: 2564,
        height: 1284,
        alt: `${appName} banner`,
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: `${appName} · Turn websites into APIs`,
    description: appTagline,
    images: [`https://raw.githubusercontent.com/${gitConfig.user}/${gitConfig.repo}/main/assets/reverse-api-banner.jpg`],
  },
  robots: {
    index: true,
    follow: true,
  },
};

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
});

const fraunces = Fraunces({
  subsets: ['latin'],
  variable: '--font-fraunces',
  axes: ['opsz', 'SOFT', 'WONK'],
});

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} ${fraunces.variable}`}
      suppressHydrationWarning
    >
      <body className="flex flex-col min-h-screen font-sans bg-cream text-ink">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
