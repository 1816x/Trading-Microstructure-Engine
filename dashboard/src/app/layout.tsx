import type { Metadata } from "next";
import "./globals.css";

import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "Trading Microstructure Engine",
  description:
    "Microstructure metric charts and the trade journal, over the backtest API.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <header className="border-b border-hairline">
          <div className="mx-auto flex w-full max-w-6xl items-baseline gap-6 px-6 py-4">
            <span className="text-sm font-semibold tracking-wide">
              Trading Microstructure Engine
            </span>
            <Nav />
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-6">{children}</main>
        <footer className="mx-auto w-full max-w-6xl px-6 py-4 text-xs text-muted">
          Synthetic sample data. Behavioral analysis only — not financial advice, no
          price predictions.
        </footer>
      </body>
    </html>
  );
}
