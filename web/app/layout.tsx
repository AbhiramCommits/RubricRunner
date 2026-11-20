import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RubricRunner",
  description: "Auditable AI-assisted assignment feedback for instructors",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
              <a href="/" className="text-lg font-semibold tracking-tight text-slate-900">
                Rubric<span className="text-indigo-600">Runner</span>
              </a>
              <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
                instructor console
              </span>
            </div>
          </header>
          <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
