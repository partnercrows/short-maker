import { useState } from "react";
import type { RecipeAudioMode, RecipeFramingMode } from "./api";
import { t, type Language } from "./i18n";

interface Props {
  lang: Language;
  estimatedDuration: number;
  faceless: boolean;
  busy: boolean;
  onCancel: () => void;
  onGenerate: (audioMode: RecipeAudioMode, volumePercent: number, framing: RecipeFramingMode) => void;
}

/** Asked only once the timeline is approved (PRD S25): audio is a render-time
 *  decision, and changing it later costs a remux, not a re-analysis. */
export default function RecipeGenerateDialog({
  lang,
  estimatedDuration,
  faceless,
  busy,
  onCancel,
  onGenerate,
}: Props) {
  const [audioMode, setAudioMode] = useState<RecipeAudioMode>("lower");
  const [volume, setVolume] = useState(20);
  const [framing, setFraming] = useState<RecipeFramingMode>("crop");

  const framings: { value: RecipeFramingMode; label: string; hint: string }[] = [
    { value: "crop", label: t(lang, "recipe_framing_crop"), hint: t(lang, "recipe_framing_crop_hint") },
    { value: "balanced", label: t(lang, "recipe_framing_balanced"), hint: t(lang, "recipe_framing_balanced_hint") },
    { value: "fit", label: t(lang, "recipe_framing_fit"), hint: t(lang, "recipe_framing_fit_hint") },
  ];

  const options: { value: RecipeAudioMode; label: string; hint?: string }[] = [
    { value: "keep", label: t(lang, "recipe_audio_keep") },
    { value: "lower", label: t(lang, "recipe_audio_lower"), hint: t(lang, "recipe_audio_lower_hint") },
    { value: "mute", label: t(lang, "recipe_audio_mute"), hint: t(lang, "recipe_audio_mute_hint") },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-5 shadow-xl dark:border-neutral-800 dark:bg-neutral-900"
      >
        <h3 className="text-base font-semibold">{t(lang, "recipe_generate_settings")}</h3>

        <div className="mt-3 rounded bg-neutral-100 p-3 text-sm dark:bg-neutral-800">
          <div className="flex justify-between">
            <span className="text-neutral-500">{t(lang, "recipe_format")}</span>
            <span>9:16</span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-500">{t(lang, "recipe_estimated_duration")}</span>
            <span>{Math.round(estimatedDuration)}s</span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-500">{t(lang, "recipe_faceless")}</span>
            <span>{faceless ? "ON" : "OFF"}</span>
          </div>
        </div>

        <div className="mt-4">
          <div className="mb-1 text-xs font-medium text-neutral-600 dark:text-neutral-400">
            {t(lang, "recipe_framing")}
          </div>
          <div className="flex gap-2">
            {framings.map((option) => (
              <button
                key={option.value}
                className={`flex-1 rounded px-2 py-1.5 text-xs disabled:opacity-50 ${
                  framing === option.value
                    ? "bg-purple-600 text-white"
                    : "border border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                }`}
                disabled={busy}
                onClick={() => setFraming(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-neutral-500">
            {framings.find((option) => option.value === framing)?.hint}
          </p>
        </div>

        <div className="mt-4">
          <div className="mb-1 text-xs font-medium text-neutral-600 dark:text-neutral-400">
            {t(lang, "recipe_audio")}
          </div>
          <div className="space-y-2">
            {options.map((option) => (
              <label
                key={option.value}
                className="flex cursor-pointer items-start gap-2 rounded border border-neutral-200 p-2 text-sm dark:border-neutral-800"
              >
                <input
                  type="radio"
                  name="audio-mode"
                  className="mt-1"
                  checked={audioMode === option.value}
                  disabled={busy}
                  onChange={() => setAudioMode(option.value)}
                />
                <span>
                  {option.label}
                  {option.hint && <span className="block text-xs text-neutral-500">{option.hint}</span>}
                </span>
              </label>
            ))}
          </div>

          {audioMode === "lower" && (
            <div className="mt-3">
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={volume}
                disabled={busy}
                onChange={(e) => setVolume(Number(e.target.value))}
                className="w-full"
              />
              <div className="text-right text-xs text-neutral-500">{volume}%</div>
            </div>
          )}
        </div>

        <p className="mt-3 text-xs text-neutral-500">{t(lang, "recipe_regenerate_hint")}</p>

        <div className="mt-4 flex justify-end gap-2">
          <button
            className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
            onClick={onCancel}
            disabled={busy}
          >
            {t(lang, "cancel")}
          </button>
          <button
            className="rounded bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
            onClick={() => onGenerate(audioMode, volume, framing)}
            disabled={busy}
          >
            {busy ? t(lang, "recipe_generating") : t(lang, "recipe_generate")}
          </button>
        </div>
      </div>
    </div>
  );
}
