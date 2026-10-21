"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

const NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/library", label: "Library", icon: "library" },
  { href: "/lesson", label: "Lesson", icon: "lesson" },
  { href: "/practice", label: "Practice", icon: "practice" },
  { href: "/progress", label: "Progress", icon: "progress" },
];

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Left rail on wide screens, bottom tab bar on phones. The skip link jumps
 * past the navigation for keyboard and screen reader users.
 */
export function AppShell({ children, userName }: { children: ReactNode; userName?: string | null }) {
  const pathname = usePathname() ?? "";
  return (
    <div className="flex min-h-dvh flex-col lg:flex-row">
      <a
        href="#main"
        className="sr-only z-50 rounded-[10px] bg-accent px-4 py-3 font-semibold text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to content
      </a>

      <nav
        aria-label="Main"
        className="hidden w-60 shrink-0 flex-col border-r border-border bg-card px-4 py-6 lg:sticky lg:top-0 lg:flex lg:h-dvh"
      >
        <Link href="/library" className="mb-8 flex min-h-11 items-center gap-2 px-2">
          <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-board font-hand text-xl text-chalk">
            S
          </span>
          <span className="text-lg font-bold tracking-tight text-text">Slate</span>
        </Link>
        <ul className="flex flex-col gap-1">
          {NAV.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-11 items-center gap-3 rounded-[10px] px-3 text-sm font-semibold transition-colors ${
                    active ? "bg-accent-tint text-accent-tint-text" : "text-text-2 hover:bg-hover hover:text-text"
                  }`}
                >
                  <Icon name={item.icon} />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
        {userName && (
          <p className="mt-auto truncate px-3 text-xs text-muted" title={userName}>
            Signed in as {userName}
          </p>
        )}
      </nav>

      <header className="sticky top-0 z-30 flex min-h-14 items-center gap-2 border-b border-border bg-page/95 px-4 backdrop-blur lg:hidden">
        <span aria-hidden className="grid h-7 w-7 place-items-center rounded-md bg-board font-hand text-lg text-chalk">
          S
        </span>
        <span className="font-bold text-text">Slate</span>
      </header>

      <main id="main" tabIndex={-1} className="min-w-0 flex-1 px-4 pb-28 pt-6 sm:px-6 lg:px-10 lg:pb-12 lg:pt-8">
        {children}
      </main>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        <ul className="grid grid-cols-4">
          {NAV.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs font-semibold ${
                    active ? "text-accent-light" : "text-muted hover:text-text"
                  }`}
                >
                  <Icon name={item.icon} />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
