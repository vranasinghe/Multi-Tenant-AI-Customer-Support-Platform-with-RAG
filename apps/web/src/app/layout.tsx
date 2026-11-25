import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@acs/ui/globals.css";

export const metadata: Metadata = {
  title: "Support Platform",
  description: "AI customer support chatbot platform",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-dvh font-sans">{children}</body>
    </html>
  );
}
