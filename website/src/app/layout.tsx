import './global.css';
import { Inter, JetBrains_Mono, Fraunces } from 'next/font/google';
import type { Metadata } from 'next';
import { appName, appTagline } from '@/lib/shared';
import { Providers } from '@/components/providers';

export const metadata: Metadata = {
  applicationName: appName,
  title: appName,
  description: appTagline,
  keywords: ['reverse API', 'API client'],
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
