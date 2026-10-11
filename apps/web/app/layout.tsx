import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Story-to-Vision — Creator Studio",
  description: "Shape a story into a cinematic episodic screenplay.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
