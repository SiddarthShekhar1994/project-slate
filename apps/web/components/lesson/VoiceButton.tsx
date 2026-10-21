"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/shared/ui/Icon";
import { ApiError, api } from "@/lib/api";

const MAX_SECONDS = 30;

type State = "idle" | "recording" | "transcribing";

/**
 * Record a spoken question and hand back its text. Shown only when the
 * browser can record and the server has a speech provider. Recording stops
 * on a second press, on Escape, or after 30 seconds.
 */
export function VoiceButton({
  disabled,
  onText,
  onMessage,
}: {
  disabled?: boolean;
  onText: (text: string) => void;
  onMessage: (message: string, isError?: boolean) => void;
}) {
  const [available, setAvailable] = useState(false);
  const [state, setState] = useState<State>("idle");
  const recorder = useRef<MediaRecorder | null>(null);
  const stopTimer = useRef<number | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !("MediaRecorder" in window) || !navigator.mediaDevices?.getUserMedia) return;
    let cancelled = false;
    api
      .voiceStatus()
      .then((s) => !cancelled && setAvailable(s.available))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (state !== "recording") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") stop();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state]);

  // Release the microphone if the panel goes away mid-recording.
  useEffect(() => () => recorder.current?.stream.getTracks().forEach((t) => t.stop()), []);

  function stop() {
    if (stopTimer.current) window.clearTimeout(stopTimer.current);
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  async function start() {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      onMessage("Microphone access is blocked. Allow it in your browser, or type your question.", true);
      return;
    }
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(stream);
    recorder.current = rec;
    rec.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    rec.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setState("transcribing");
      onMessage("Working out what you said…");
      try {
        const { text } = await api.transcribe(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
        onText(text);
        onMessage("Here's what Slate heard. Fix anything it got wrong, then press Ask.");
      } catch (e) {
        onMessage(e instanceof ApiError ? e.message : "Couldn't make out that recording. Try again.", true);
      } finally {
        setState("idle");
      }
    };
    rec.start();
    setState("recording");
    onMessage(`Listening. Press the button again or Escape when you're done.`);
    stopTimer.current = window.setTimeout(stop, MAX_SECONDS * 1000);
  }

  if (!available) return null;
  const recording = state === "recording";
  return (
    <button
      type="button"
      onClick={() => (recording ? stop() : void start())}
      disabled={disabled || state === "transcribing"}
      aria-pressed={recording}
      aria-label={recording ? "Stop recording" : "Ask by voice"}
      className={`inline-flex min-h-12 min-w-12 items-center justify-center gap-2 rounded-[10px] border px-3 text-sm font-semibold ${
        recording
          ? "border-warning/50 bg-warning-bg text-warning"
          : "border-border bg-raised text-text-2 hover:bg-hover hover:text-text"
      } disabled:opacity-50`}
    >
      {recording ? (
        <>
          <span aria-hidden className="h-2.5 w-2.5 rounded-full bg-warning motion-safe:animate-pulse" />
          <Icon name="stop" size={18} />
        </>
      ) : (
        <Icon name="mic" size={20} />
      )}
      <span className="sm:sr-only">{recording ? "Stop" : state === "transcribing" ? "Working…" : "Speak"}</span>
    </button>
  );
}
