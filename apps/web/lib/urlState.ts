"use client";

/**
 * Shallow URL updates. Next 16 integrates history.replaceState with
 * useSearchParams, so this updates the URL without a navigation.
 */
export function replaceQuery(updates: Record<string, string | null>) {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(updates)) {
    if (value === null) url.searchParams.delete(key);
    else url.searchParams.set(key, value);
  }
  window.history.replaceState(null, "", `${url.pathname}?${url.searchParams.toString()}`);
}
