"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";

/**
 * Only same-origin paths are allowed as the post-login destination. Parsing the
 * URL catches tricks like "/\\evil.com", which browsers read as "//evil.com".
 */
export function safeNext(raw: string | null, origin = window.location.origin): string {
  if (!raw || !raw.startsWith("/")) return "/library";
  try {
    const url = new URL(raw, origin);
    if (url.origin !== origin) return "/library";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/library";
  }
}

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const search = useSearchParams();
  const { refresh } = useSession();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const next = safeNext(search?.get("next") ?? null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") await api.signup(email, password, String(form.get("name") ?? ""));
      else await api.login(email, password);
      await refresh();
      router.replace(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  const other = mode === "login" ? "/signup" : "/login";
  const field =
    "min-h-12 rounded-[10px] border border-border bg-raised px-4 text-base text-text placeholder:text-muted/70 focus-visible:border-accent-light";

  return (
    <main id="main" className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3">
          <span aria-hidden className="grid h-10 w-10 place-items-center rounded-xl bg-board font-hand text-2xl text-chalk">
            S
          </span>
          <span className="text-2xl font-bold tracking-tight">Slate</span>
        </div>
        <h1 className="text-2xl font-bold text-text">{mode === "login" ? "Sign in" : "Create your account"}</h1>
        <p className="mt-2 text-sm text-text-2">
          {mode === "login"
            ? "Pick up your lessons and practice where you left off."
            : "Your account keeps your sources, practice history and review schedule."}
        </p>
        <form className="mt-6 flex flex-col gap-4" onSubmit={onSubmit} noValidate={false}>
          {mode === "signup" && (
            <label className="flex flex-col gap-1.5 text-sm font-semibold text-text-2">
              Name
              <input name="name" autoComplete="name" className={field} maxLength={80} />
            </label>
          )}
          <label className="flex flex-col gap-1.5 text-sm font-semibold text-text-2">
            Email
            <input name="email" type="email" autoComplete="email" required className={field} />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-semibold text-text-2">
            Password
            <input
              name="password"
              type="password"
              required
              minLength={mode === "signup" ? 8 : undefined}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              className={field}
              aria-describedby={mode === "signup" ? "password-help" : undefined}
            />
            {mode === "signup" && (
              <span id="password-help" className="text-xs font-normal text-muted">
                At least 8 characters.
              </span>
            )}
          </label>
          <div aria-live="assertive">
            {error && (
              <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-3 py-2 text-sm text-warning">
                {error}
              </p>
            )}
          </div>
          <button
            type="submit"
            disabled={busy}
            className="min-h-12 rounded-[10px] bg-accent text-sm font-semibold text-white hover:bg-[#3557f0] disabled:bg-raised disabled:text-muted"
          >
            {busy ? "One moment…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        <p className="mt-6 text-sm text-text-2">
          {mode === "login" ? "New to Slate? " : "Already have an account? "}
          <Link
            href={`${other}${next !== "/library" ? `?next=${encodeURIComponent(next)}` : ""}`}
            className="font-semibold text-accent-light underline-offset-4 hover:underline"
          >
            {mode === "login" ? "Create an account" : "Sign in"}
          </Link>
        </p>
      </div>
    </main>
  );
}
