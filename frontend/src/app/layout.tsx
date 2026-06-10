import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Local RAG",
  description: "Air-gapped local RAG over PDFs",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
