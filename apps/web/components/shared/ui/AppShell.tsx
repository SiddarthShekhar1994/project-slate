"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { isWriting, topicHref, useTopics } from "@/lib/topics";
import type { MasteryStatus } from "@/lib/types";
import { Icon, type IconName } from "./Icon";

type NavItem = { href: string; label: string; icon: IconName };

const HOME: NavItem = { href: "/dashboard", label: "Dashboard", icon: "dashboard" };
const MORE: NavItem[] = [
  { href: "/progress", label: "Progress", icon: "progress" },
  { href: "/library", label: "Sources", icon: "library" },
];
// The desktop app has no server to configure, so API keys get a page of their own.
const SETTINGS: NavItem = { href: "/settings", label: "Settings", icon: "settings" };

const DOT: Record<MasteryStatus, string> = {
  new: "border border-border bg-raised",
  learning: "bg-warning",
  practiced: "bg-accent-light",
  mastered: "bg-success",
};

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

const linkClasses = (active: boolean) =>
  `flex min-h-11 items-center gap-3 rounded-[10px] px-3 text-sm font-semibold transition-colors ${
    active ? "bg-accent-tint text-accent-tint-text" : "text-text-2 hover:bg-hover hover:text-text"
  }`;

/** The student's topics, each its own tab, in the order they arrived. */
function TopicLinks({ pathname }: { pathname: string }) {
  const { dashboard } = useTopics();
  const topics = dashboard?.topics ?? [];
  return (
    <section aria-labelledby="nav-topics" className="mt-6 flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-3">
        <h2 id="nav-topics" className="text-xs font-semibold tracking-wide text-muted uppercase">
          Your topics
        </h2>
        <Link
          href="/dashboard#add-topic"
          className="-mr-2 grid min-h-11 min-w-11 place-items-center rounded-[10px] text-text-2 hover:bg-hover hover:text-text"
        >
          <Icon name="plus" size={18} />
          <span className="sr-only">Add a topic</span>
        </Link>
      </div>
      {topics.length === 0 ? (
        <p className="px-3 text-xs text-muted">Upload a study guide or add a topic, and it shows up here.</p>
      ) : (
        <ul className="-mx-1 flex min-h-0 flex-col gap-0.5 overflow-y-auto px-1 pb-2">
          {topics.map((topic) => {
            const href = topicHref(topic.id);
            const active = pathname === href;
            return (
              <li key={topic.id}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-11 items-center gap-3 rounded-[10px] px-3 text-sm transition-colors ${
                    active ? "bg-accent-tint font-semibold text-accent-tint-text" : "text-text-2 hover:bg-hover hover:text-text"
                  }`}
                >
                  <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT[topic.status]}`} />
                  <span className="min-w-0 flex-1 truncate">{topic.title}</span>
                  {isWriting(topic) && (
                    <span className="shrink-0 text-xs text-muted" title="Slate is writing this topic's lesson">
                      <span aria-hidden className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-muted border-t-transparent motion-reduce:animate-none" />
                      <span className="sr-only">(being written)</span>
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/**
 * Left rail on wide screens, bottom tab bar on phones. The skip link jumps
 * past the navigation for keyboard and screen reader users.
 */
export function AppShell({
  children,
  userName,
  desktop = false,
}: {
  children: ReactNode;
  userName?: string | null;
  desktop?: boolean;
}) {
  const pathname = usePathname() ?? "";
  const more = desktop ? [...MORE, SETTINGS] : MORE;
  const tabs = [HOME, ...more];
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
        className="hidden w-64 shrink-0 flex-col border-r border-border bg-card px-4 py-6 lg:sticky lg:top-0 lg:flex lg:h-dvh"
      >
        <Link href="/dashboard" className="mb-6 flex min-h-11 items-center gap-2 px-2">
          <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-board font-hand text-xl text-chalk">
            S
          </span>
          <span className="text-lg font-bold tracking-tight text-text">Slate</span>
        </Link>
        <Link
          href={HOME.href}
          aria-current={isActive(pathname, HOME.href) ? "page" : undefined}
          className={linkClasses(isActive(pathname, HOME.href))}
        >
          <Icon name={HOME.icon} />
          {HOME.label}
        </Link>
        <TopicLinks pathname={pathname} />
        <ul className="mt-4 flex flex-col gap-1 border-t border-border pt-4">
          {more.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <li key={item.href}>
                <Link href={item.href} aria-current={active ? "page" : undefined} className={linkClasses(active)}>
                  <Icon name={item.icon} />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
        {desktop ? (
          <p className="mt-4 px-3 text-xs text-muted">Everything stays on this computer.</p>
        ) : (
          userName && (
            <p className="mt-4 truncate px-3 text-xs text-muted" title={userName}>
              Signed in as {userName}
            </p>
          )
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
        <ul className={`grid ${tabs.length === 4 ? "grid-cols-4" : "grid-cols-3"}`}>
          {tabs.map((item) => {
            const current = isActive(pathname, item.href);
            // A topic's page is reached from the dashboard, so the dashboard tab stays lit there.
            const lit = current || (item === HOME && pathname.startsWith("/topics/"));
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={current ? "page" : undefined}
                  className={`flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs font-semibold ${
                    lit ? "text-accent-light" : "text-muted hover:text-text"
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
