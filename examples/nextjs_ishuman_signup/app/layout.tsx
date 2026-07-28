import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign in with lemma.id (Next.js)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
