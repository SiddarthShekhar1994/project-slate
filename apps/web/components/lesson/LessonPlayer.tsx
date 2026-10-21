"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Board } from "@/components/shared/board/Board";
import { buttonClasses } from "@/components/shared/ui/Button";
import { Icon } from "@/components/shared/ui/Icon";
import { api } from "@/lib/api";
import { boardStateAt, currentWord, estimateTimings, spokenText, stepDuration } from "@/lib/lesson/timeline";
import type { WordTiming } from "@/lib/lesson/types";
import type { LessonView, StepAudio } from "@/lib/types";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { replaceQuery } from "@/lib/urlState";
import { AskPanel } from "./AskPanel";
import { Caption } from "./Caption";
import { CheckpointCard } from "./CheckpointCard";

export const SPEEDS = [0.75, 1, 1.25, 1.5] as const;

type Props = {
  lesson: LessonView;
  initialStep: number;
  initialSpeed: number;
  initialVoice: string | null;
  initialCaptions: boolean;
};

const isTyping = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));

/**
 * The lesson player. A requestAnimationFrame clock gives the time into the
 * current step; when a voice is playing the clock is the audio element itself,
 * so the board and captions follow the speech exactly. Everything on screen is
 * derived from (step, time) by ``boardStateAt``.
 */
export function LessonPlayer({ lesson, initialStep, initialSpeed, initialVoice, initialCaptions }: Props) {
  const script = lesson.script;
  const steps = script.steps;
  const reducedMotion = useReducedMotion();

  const [step, setStep] = useState(Math.min(Math.max(initialStep, 0), steps.length - 1));
  const [t, setTState] = useState(0);
  // The clock reads and writes time through a ref so each frame builds on the last.
  const tRef = useRef(0);
  const setT = useCallback((value: number) => {
    tRef.current = value;
    setTState(value);
  }, []);
  const [playing, setPlaying] = useState(false);
  const playingRef = useRef(false);
  useEffect(() => {
    playingRef.current = playing;
  }, [playing]);
  const [speed, setSpeed] = useState(initialSpeed);
  const [voice, setVoice] = useState<string | null>(
    lesson.tts.available ? (initialVoice ?? lesson.tts.default_voice) : null,
  );
  const [captions, setCaptions] = useState(initialCaptions);
  const [audio, setAudio] = useState<Record<string, StepAudio>>({});
  const [checkpointOpen, setCheckpointOpen] = useState(false);
  const [answered, setAnswered] = useState<Set<number>>(new Set());
  const [finished, setFinished] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  const audioKey = (s: number) => `${voice}:${s}`;
  const stepAudio = voice ? audio[audioKey(step)] : undefined;
  const voiced = stepAudio?.status === "ok";

  // Word timings per step: from the voice when we have it, otherwise estimated.
  const timingsFor = useCallback(
    (s: number): WordTiming[] => {
      const a = voice ? audio[`${voice}:${s}`] : undefined;
      return a?.status === "ok" ? a.words : estimateTimings(steps[s].narration);
    },
    [audio, steps, voice],
  );
  const timings = useMemo(() => timingsFor(step), [timingsFor, step]);
  const duration = useMemo(() => stepDuration(steps[step], timings), [steps, step, timings]);

  // Fetch (and the server caches) audio for this step and the next. Requests
  // in flight are tracked per step and left running when other audio arrives:
  // cancelling them on every update could drop a response mid-read, and
  // nothing would ask for that step again.
  const inflight = useRef(new Map<string, AbortController>());
  useEffect(() => {
    if (!voice) return;
    for (const s of [step, step + 1]) {
      const key = `${voice}:${s}`;
      if (s >= steps.length || audio[key] || inflight.current.has(key)) continue;
      const controller = new AbortController();
      inflight.current.set(key, controller);
      api
        .stepAudio(lesson.id, s, voice, controller.signal)
        .then((result) => setAudio((prev) => ({ ...prev, [key]: result })))
        .catch(() => undefined)
        .finally(() => {
          if (inflight.current.get(key) === controller) inflight.current.delete(key);
        });
    }
  }, [voice, step, steps.length, lesson.id, audio]);

  // A different voice or lesson makes pending requests pointless.
  useEffect(() => {
    const pending = inflight.current;
    return () => {
      for (const controller of pending.values()) controller.abort();
      pending.clear();
    };
  }, [voice, lesson.id]);

  // Keep the URL in step with what is on screen.
  useEffect(() => {
    replaceQuery({
      step: String(step + 1),
      speed: speed === 1 ? null : String(speed),
      voice: voice && voice !== lesson.tts.default_voice ? voice : null,
      cc: captions ? null : "0",
    });
  }, [step, speed, voice, captions, lesson.tts.default_voice]);

  useEffect(() => {
    void api.saveLessonProgress(lesson.id, step).catch(() => undefined);
  }, [lesson.id, step]);

  // Point the audio element at this step's audio.
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (voiced && stepAudio.status === "ok") {
      if (!el.src.endsWith(stepAudio.url)) {
        // A new source pauses the element, so resume if the lesson is playing
        // (moving on to the next step does not toggle ``playing``).
        el.src = stepAudio.url;
        el.currentTime = tRef.current / 1000;
        if (playingRef.current) void el.play().catch(() => setPlaying(false));
      }
    } else {
      el.removeAttribute("src");
    }
  }, [voiced, stepAudio]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = speed;
  }, [speed]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !voiced) return;
    if (playing) void el.play().catch(() => setPlaying(false));
    else el.pause();
  }, [playing, voiced]);

  const goTo = useCallback(
    (next: number, keepPlaying = false) => {
      const clamped = Math.max(0, Math.min(steps.length - 1, next));
      setStep(clamped);
      setT(0);
      setCheckpointOpen(false);
      setFinished(false);
      if (audioRef.current) audioRef.current.currentTime = 0;
      setPlaying(keepPlaying);
    },
    [steps.length, setT],
  );

  const endOfStep = useCallback(() => {
    if (steps[step].checkpoint && !answered.has(step)) {
      setPlaying(false);
      setCheckpointOpen(true);
      return;
    }
    if (step < steps.length - 1) goTo(step + 1, true);
    else {
      setPlaying(false);
      setFinished(true);
    }
  }, [answered, goTo, step, steps]);

  // The clock.
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const el = audioRef.current;
      let next: number;
      if (voiced && el) {
        next = el.currentTime * 1000;
        if (el.ended) next = Math.max(next, duration);
      } else {
        next = tRef.current + (now - last) * speed;
      }
      last = now;
      if (next >= duration) {
        setT(duration);
        endOfStep();
        return;
      }
      setT(next);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, voiced, duration, speed, endOfStep, setT]);

  const togglePlay = useCallback(() => {
    if (checkpointOpen) return;
    if (finished) {
      goTo(0, true);
      return;
    }
    if (t >= duration) {
      endOfStep();
      return;
    }
    setPlaying((p) => !p);
  }, [checkpointOpen, finished, goTo, t, duration, endOfStep]);

  // Keyboard: space or k plays and pauses, arrows change step, c toggles captions.
  // Shortcuts only work while focus is inside the player (WCAG 2.1.4), so they
  // never fire from speech input or typing elsewhere on the page.
  const playerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = playerRef.current;
    if (!root) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      const onButton = event.target instanceof HTMLButtonElement;
      if ((event.key === " " && !onButton) || event.key === "k") {
        event.preventDefault();
        togglePlay();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        if (!checkpointOpen) goTo(step + 1, playing);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        goTo(step - 1, playing);
      } else if (event.key === "c") {
        setCaptions((c) => !c);
      }
    };
    root.addEventListener("keydown", onKey);
    return () => root.removeEventListener("keydown", onKey);
  }, [togglePlay, goTo, step, playing, checkpointOpen]);

  const board = useMemo(
    () => boardStateAt(script, step, t, timingsFor, reducedMotion),
    [script, step, t, timingsFor, reducedMotion],
  );
  const word = currentWord(timings, t);
  const current = steps[step];
  const progress = Math.min(1, t / duration);

  function answerCheckpoint() {
    setAnswered((prev) => new Set(prev).add(step));
    setCheckpointOpen(false);
    if (step < steps.length - 1) goTo(step + 1, true);
    else setFinished(true);
  }

  return (
    <div ref={playerRef} className="flex min-w-0 flex-col gap-4">
      <audio ref={audioRef} preload="auto" className="hidden" />

      {/* Focusable so keyboard users can land on the board and use the shortcuts. */}
      <div tabIndex={0} aria-describedby="player-keys" className="rounded-[14px]">
        <Board state={board} label={`Board for step ${step + 1}: ${current.title}`} />
      </div>

      {/* Screen readers get each step's full narration once, when it starts. */}
      <p className="sr-only" aria-live="polite">
        Step {step + 1} of {steps.length}, {current.title}. {spokenText(current.narration)}
      </p>

      {captions && (
        <div className="min-h-14 rounded-[10px] border border-border bg-card px-4 py-3">
          <Caption narration={current.narration} word={word} />
        </div>
      )}

      {checkpointOpen && current.checkpoint && (
        <CheckpointCard
          key={step}
          lessonId={lesson.id}
          step={step}
          checkpoint={current.checkpoint}
          onContinue={answerCheckpoint}
        />
      )}

      {finished && (
        <div className="flex flex-col gap-3 rounded-[14px] border border-success/40 bg-success-bg p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-semibold text-success">Lesson complete</p>
            <p className="text-sm text-text-2">Lock it in with a worksheet, easy to hard.</p>
          </div>
          <PracticeButton skillId={lesson.skill.id} title={lesson.skill.title} />
        </div>
      )}

      <Controls
        steps={steps.map((s) => s.title)}
        step={step}
        progress={progress}
        playing={playing}
        disabled={checkpointOpen}
        speed={speed}
        voice={voice}
        voices={lesson.tts.voices}
        ttsAvailable={lesson.tts.available}
        voiceStatus={voice ? (stepAudio ? (stepAudio.status === "ok" ? "ready" : "unavailable") : "loading") : "off"}
        captions={captions}
        onToggle={togglePlay}
        onPrev={() => goTo(step - 1, playing)}
        onNext={() => goTo(step + 1, playing)}
        onSeek={(s) => goTo(s, playing)}
        onSpeed={setSpeed}
        onVoice={setVoice}
        onCaptions={() => setCaptions((c) => !c)}
      />

      <AskPanel lessonId={lesson.id} step={step} stepTitle={current.title} />
    </div>
  );
}

/** Builds a worksheet for the lesson's skill and goes straight to it. */
function PracticeButton({ skillId, title }: { skillId: string; title: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex flex-col items-start gap-1">
      <button
        type="button"
        disabled={busy}
        className={buttonClasses("primary")}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const sheet = await api.createWorksheet([skillId]);
            router.push(`/practice/${sheet.id}`);
          } catch {
            setError("Couldn't build a worksheet. Try again.");
            setBusy(false);
          }
        }}
      >
        {busy ? "Building…" : `Practice ${title.toLowerCase()}`}
      </button>
      {error && (
        <p role="alert" className="text-xs text-warning">
          {error}
        </p>
      )}
    </div>
  );
}

type ControlsProps = {
  steps: string[];
  step: number;
  progress: number;
  playing: boolean;
  disabled: boolean;
  speed: number;
  voice: string | null;
  voices: { id: string; label: string }[];
  ttsAvailable: boolean;
  voiceStatus: "ready" | "loading" | "unavailable" | "off";
  captions: boolean;
  onToggle: () => void;
  onPrev: () => void;
  onNext: () => void;
  onSeek: (step: number) => void;
  onSpeed: (speed: number) => void;
  onVoice: (voice: string | null) => void;
  onCaptions: () => void;
};

function Controls(props: ControlsProps) {
  const { steps, step, progress, playing, disabled } = props;
  const iconButton =
    "grid h-11 w-11 shrink-0 place-items-center rounded-[10px] text-text-2 hover:bg-hover hover:text-text disabled:opacity-40";
  const select =
    "min-h-11 rounded-[10px] border border-border bg-raised px-3 text-sm text-text hover:bg-hover disabled:opacity-50";
  return (
    <div className="flex flex-col gap-3 rounded-[14px] border border-border bg-card p-3 sm:p-4">
      <div className="flex items-center gap-1">
        <button type="button" className={iconButton} onClick={props.onPrev} disabled={step === 0} aria-label="Previous step">
          <Icon name="prev" />
        </button>
        <button
          type="button"
          onClick={props.onToggle}
          disabled={disabled}
          aria-label={playing ? "Pause" : "Play"}
          className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent text-white hover:bg-[#3557f0] disabled:bg-raised disabled:text-muted"
        >
          <Icon name={playing ? "pause" : "play"} />
        </button>
        <button
          type="button"
          className={iconButton}
          onClick={props.onNext}
          disabled={step === steps.length - 1 || disabled}
          aria-label="Next step"
        >
          <Icon name="next" />
        </button>
        <p className="ml-2 min-w-0 truncate text-sm text-text-2">
          <span className="font-semibold text-text">
            Step {step + 1} of {steps.length}
          </span>{" "}
          · {steps[step]}
        </p>
      </div>

      {/* Each step stays a 44px target; on narrow screens the row scrolls instead of shrinking. */}
      <ol className="-mx-1 flex gap-1 overflow-x-auto px-1" aria-label="Steps">
        {steps.map((title, i) => (
          <li key={i} className="min-w-11 flex-1">
            <button
              type="button"
              onClick={() => props.onSeek(i)}
              disabled={disabled}
              aria-label={`Step ${i + 1}: ${title}`}
              aria-current={i === step ? "step" : undefined}
              className="group flex h-11 w-full items-center disabled:cursor-not-allowed"
            >
              <span className="relative h-2 w-full overflow-hidden rounded-full bg-raised group-hover:bg-hover">
                <span
                  className="absolute inset-y-0 left-0 rounded-full bg-accent-light"
                  style={{ width: i < step ? "100%" : i === step ? `${progress * 100}%` : "0%" }}
                />
              </span>
            </button>
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm text-text-2">
          Speed
          <select className={select} value={props.speed} onChange={(e) => props.onSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}x
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-text-2">
          Voice
          <select
            className={select}
            value={props.voice ?? ""}
            onChange={(e) => props.onVoice(e.target.value || null)}
            disabled={!props.ttsAvailable}
          >
            {props.ttsAvailable ? (
              <>
                {props.voices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
                <option value="">Off (captions only)</option>
              </>
            ) : (
              <option value="">Off: no voice service set up</option>
            )}
          </select>
        </label>
        {props.voiceStatus === "loading" && <span className="text-xs text-muted">Preparing voice…</span>}
        {props.voiceStatus === "unavailable" && <span className="text-xs text-warning">Voice unavailable, using captions</span>}
        <button
          type="button"
          onClick={props.onCaptions}
          aria-pressed={props.captions}
          className={`ml-auto min-h-11 rounded-[10px] border px-3 text-sm font-semibold ${
            props.captions ? "border-accent-light/50 bg-accent-tint text-accent-tint-text" : "border-border text-text-2 hover:bg-hover"
          }`}
        >
          Captions {props.captions ? "on" : "off"}
        </button>
      </div>
      <p id="player-keys" className="hidden text-xs text-muted sm:block">
        With the board or a control focused: <kbd className="font-mono">Space</kbd> play or pause, <kbd className="font-mono">←</kbd>{" "}
        <kbd className="font-mono">→</kbd> step, <kbd className="font-mono">C</kbd> captions.
      </p>
    </div>
  );
}
