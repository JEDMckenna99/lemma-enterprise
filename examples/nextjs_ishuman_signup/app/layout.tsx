import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Verify a lemma proof (Next.js)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
