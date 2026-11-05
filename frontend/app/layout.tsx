import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PRAGMATA - Bug Investigation & Resolution Platform",
  description: "Investigate. Deliberate. Resolve. Collaborative multi-agent bug resolution.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
