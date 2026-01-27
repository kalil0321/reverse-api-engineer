import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Reverse API Engineer",
  description: "Cloud-based API client generation from browser traffic",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
