"use client";

import { useEffect, useState } from "react";

/**
 * Seconds left until ``endsAt``, ticking once a second. ``serverNow`` is the
 * server's clock when the data was fetched; the difference from the browser's
 * clock is subtracted so a wrong device clock doesn't eat into the exam.
 */
export function useCountdown(endsAt: string | null, serverNow: string | null): number | null {
  const [offset] = useState(() => (serverNow ? Date.parse(serverNow) - Date.now() : 0));
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!endsAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [endsAt]);

  if (!endsAt) return null;
  return Math.max(0, Math.round((Date.parse(endsAt) - (now + offset)) / 1000));
}
