"use client";

import { type FormEvent, useId, useState } from "react";
import { Button } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { ApiError, api } from "@/lib/api";
import type { AppSettings, KeyName, SettingsChanges } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const KEYS: { name: KeyName; label: string; what: string; where: string; url: string }[] = [
  {
    name: "anthropic_api_key",
    label: "Claude (Anthropic) API key",
    what: "Writes lessons from your course materials, answers your questions, and reads photos and scanned pages.",
    where: "console.anthropic.com",
    url: "https://console.anthropic.com/settings/keys",
  },
  {
    name: "elevenlabs_api_key",
    label: "ElevenLabs API key",
    what: "The narrated voice in lessons, and spoken questions.",
    where: "elevenlabs.io",
    url: "https://elevenlabs.io/app/settings/api-keys",
  },
  {
    name: "openai_api_key",
    label: "OpenAI API key",
    what: "Another option for the narrated voice and spoken questions.",
    where: "platform.openai.com",
    url: "https://platform.openai.com/api-keys",
  },
];

/** API keys for the desktop app. Saved keys are never shown again, only their last four characters. */
export function SettingsView() {
  const { data, error, setData } = useApi(() => api.settings());
  if (!data) {
    if (error) {
      return (
        <div className="mx-auto max-w-2xl">
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="mt-2 text-text-2">
            Settings are part of the Windows app. On the website, API keys are set on the server.
          </p>
        </div>
      );
    }
    return <Spinner label="Loading settings" />;
  }
  return <SettingsForm settings={data} onSaved={setData} />;
}

function SettingsForm({ settings, onSaved }: { settings: AppSettings; onSaved: (s: AppSettings) => void }) {
  const [typed, setTyped] = useState<Partial<Record<KeyName, string>>>({});
  const [tts, setTts] = useState(settings.tts_provider);
  const [stt, setStt] = useState(settings.stt_provider);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  async function save(changes: SettingsChanges, done: string) {
    setBusy(true);
    setMessage(null);
    try {
      const saved = await api.saveSettings(changes);
      onSaved(saved);
      setTyped({});
      setMessage({ text: done, error: false });
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.message : "Couldn't save. Try again.", error: true });
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const changes: SettingsChanges = {};
    for (const [name, value] of Object.entries(typed)) if (value?.trim()) changes[name as KeyName] = value.trim();
    if (tts !== settings.tts_provider) changes.tts_provider = tts;
    if (stt !== settings.stt_provider) changes.stt_provider = stt;
    if (Object.keys(changes).length === 0) {
      setMessage({ text: "Nothing to save yet. Paste a key first.", error: false });
      return;
    }
    void save(changes, "Saved. The new keys work right away.");
  }

  const { active } = settings;
  const both = settings.keys.elevenlabs_api_key.set && settings.keys.openai_api_key.set;

  return (
    <form onSubmit={onSubmit} className="mx-auto flex max-w-2xl flex-col gap-6">
      <header>
        <p className="text-sm font-semibold text-accent-tint-text">Settings</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">API keys</h1>
        <p className="mt-2 text-text-2">
          Slate works without any keys: hints, lessons and practice come from its built-in material, and every answer
          is checked by a computer algebra system either way. Keys turn on the extras below. They stay on this
          computer.
        </p>
      </header>

      <Card aria-labelledby="status-heading" className="p-4 sm:p-5">
        <h2 id="status-heading" className="font-semibold">
          What&apos;s on
        </h2>
        <ul className="mt-2 grid gap-1 text-sm text-text-2 sm:grid-cols-3">
          <li>Claude: {active.claude ? "on" : "off"}</li>
          <li>Narrated voice: {active.voice ? NAMES[active.voice] ?? active.voice : "off"}</li>
          <li>Spoken questions: {active.transcription ? NAMES[active.transcription] ?? active.transcription : "off"}</li>
        </ul>
      </Card>

      {KEYS.map((key) => (
        <KeyField
          key={key.name}
          spec={key}
          saved={settings.keys[key.name]}
          value={typed[key.name] ?? ""}
          disabled={busy}
          onChange={(value) => setTyped((t) => ({ ...t, [key.name]: value }))}
          onRemove={() => save({ [key.name]: "" }, "Key removed.")}
        />
      ))}

      {both && (
        <Card className="flex flex-col gap-4 p-4 sm:p-5">
          <p className="text-sm text-text-2">You have both voice keys. Choose which service does what.</p>
          <Choice
            label="Narrated voice"
            value={tts}
            onChange={(v) => setTts(v as AppSettings["tts_provider"])}
            options={[
              ["", "Automatic (ElevenLabs)"],
              ["elevenlabs", "ElevenLabs"],
              ["openai", "OpenAI"],
            ]}
          />
          <Choice
            label="Spoken questions"
            value={stt}
            onChange={(v) => setStt(v as AppSettings["stt_provider"])}
            options={[
              ["", "Automatic (OpenAI)"],
              ["openai", "OpenAI"],
              ["elevenlabs", "ElevenLabs"],
            ]}
          />
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={busy} aria-busy={busy}>
          {busy ? "Saving…" : "Save"}
        </Button>
        <p aria-live="polite" className={`text-sm ${message?.error ? "text-warning" : "text-text-2"}`}>
          {message?.text ?? ""}
        </p>
      </div>

      <p className="text-xs text-muted">
        Your library, progress and these settings are saved in <span className="font-mono">{settings.data_dir}</span>.
      </p>
    </form>
  );
}

const NAMES: Record<string, string> = { elevenlabs: "ElevenLabs", openai: "OpenAI" };

function KeyField({
  spec,
  saved,
  value,
  disabled,
  onChange,
  onRemove,
}: {
  spec: (typeof KEYS)[number];
  saved: { set: boolean; hint: string };
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onRemove: () => void;
}) {
  const id = useId();
  return (
    <Card className="flex flex-col gap-2 p-4 sm:p-5">
      <label htmlFor={id} className="font-semibold">
        {spec.label}
      </label>
      <p id={`${id}-what`} className="text-sm text-text-2">
        {spec.what} Get one at{" "}
        <a href={spec.url} target="_blank" rel="noreferrer" className="text-accent-light underline">
          {spec.where}
        </a>
        .
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id={id}
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={`${id}-what ${id}-state`}
          placeholder={saved.set ? "Paste a new key to replace the saved one" : "Paste your key"}
          className="min-h-11 flex-1 rounded-[10px] border border-border bg-raised px-4 font-mono text-sm text-text placeholder:text-muted/70 focus-visible:border-accent-light"
        />
        {saved.set && (
          <Button variant="ghost" onClick={onRemove} disabled={disabled}>
            Remove<span className="sr-only"> {spec.label}</span>
          </Button>
        )}
      </div>
      <p id={`${id}-state`} className="text-xs text-muted">
        {saved.set ? `Saved (ends in ${saved.hint.replace("…", "")})` : "Not set"}
      </p>
    </Card>
  );
}

function Choice({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-11 rounded-[10px] border border-border bg-raised px-3 text-sm text-text"
      >
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
    </div>
  );
}
