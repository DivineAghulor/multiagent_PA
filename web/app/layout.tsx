import type { Metadata } from "next";
import { Suspense } from "react";
import { Nav } from "@/components/nav";
import { HealthBadge } from "@/components/health-badge";
import "./globals.css";

export const metadata: Metadata = {
  title: "Personal Assistant",
  description: "Capture, plan, decompose, do, review.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto max-w-5xl px-4 py-6">
          <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <Nav />
            {/* Suspense so a slow or dead backend delays the badge, not the page. */}
            <Suspense fallback={null}>
              <HealthBadge />
            </Suspense>
          </header>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
