import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CEML Research Assistant",
  description: "Multi-agent research assistant for CEML Lab",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className="dark">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
