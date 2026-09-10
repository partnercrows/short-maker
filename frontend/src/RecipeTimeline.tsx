import { useState } from "react";
import type { Recipe, RecipeScene } from "./api";
import { t, type Language } from "./i18n";

interface Props {
  lang: Language;
  recipe: Recipe;
  scenes: RecipeScene[];
  disabled?: boolean;
  onChange: (scenes: RecipeScene[]) => void;
}

function formatClock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function sceneLabel(scene: RecipeScene): string {
  return scene.label.replaceAll("_", " ").toLowerCase();
}

/** The cooking story, in order, with the few edits the PRD asks for: keep or
 *  drop a scene, move it, trim it. Deliberately not a video editor (PRD S19). */
export default function RecipeTimeline({ lang, recipe, scenes, disabled = false, onChange }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);

  function move(index: number, direction: -1 | 1) {
    const next = [...scenes];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  function toggleEnabled(sceneId: string) {
    onChange(scenes.map((scene) => (scene.scene_id === sceneId ? { ...scene, enabled: !scene.enabled } : scene)));
  }

  function trim(sceneId: string, field: "source_start" | "source_end", value: number) {
    onChange(
      scenes.map((scene) => {
        if (scene.scene_id !== sceneId) return scene;
        const updated = { ...scene, [field]: value };
        // A scene has to keep a length; nudge the other edge rather than
        // letting the two cross over.
        if (updated.source_end - updated.source_start < 0.5) {
          if (field === "source_start") updated.source_end = updated.source_start + 0.5;
          else updated.source_start = Math.max(0, updated.source_end - 0.5);
        }
        return updated;
      }),
    );
  }

  // Output position, so the numbers line up with the voice-over script.
  let position = 0;

  return (
    <div className="space-y-2">
      {scenes.map((scene, index) => {
        const start = position;
        const duration = Math.max(0, scene.source_end - scene.source_start);
        if (scene.enabled) position += duration;
        const warning = scene.face_check?.status === "warning";
        const reframed = scene.face_check?.status === "reframed";

        return (
          <div
            key={scene.scene_id}
            className={`rounded border p-3 ${
              scene.enabled
                ? "border-neutral-200 dark:border-neutral-800"
                : "border-dashed border-neutral-300 opacity-60 dark:border-neutral-700"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-neutral-400">{String(index + 1).padStart(2, "0")}</span>
                  <span className="font-medium">{scene.title}</span>
                  <span className="rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300">
                    {sceneLabel(scene)}
                  </span>
                  {scene.is_hook && (
                    <span className="rounded bg-purple-100 px-2 py-0.5 text-xs text-purple-700 dark:bg-purple-950 dark:text-purple-300">
                      {t(lang, "recipe_scene_hook")}
                    </span>
                  )}
                  {warning && <span className="text-xs text-amber-600 dark:text-amber-400">⚠</span>}
                </div>
                <div className="mt-1 text-xs text-neutral-500">
                  {t(lang, "recipe_source")}: {formatClock(scene.source_start)}-{formatClock(scene.source_end)} ·{" "}
                  {duration.toFixed(1)}s
                  {scene.enabled && ` · ${formatClock(start)} → ${formatClock(start + duration)}`}
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                <button
                  className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  disabled={disabled || index === 0}
                  onClick={() => move(index, -1)}
                  title={t(lang, "recipe_move_up")}
                >
                  ↑
                </button>
                <button
                  className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  disabled={disabled || index === scenes.length - 1}
                  onClick={() => move(index, 1)}
                  title={t(lang, "recipe_move_down")}
                >
                  ↓
                </button>
                <button
                  className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  disabled={disabled}
                  onClick={() => setExpanded(expanded === scene.scene_id ? null : scene.scene_id)}
                >
                  {t(lang, "recipe_trim")}
                </button>
                <button
                  className={`rounded border px-2 py-1 text-xs disabled:opacity-40 ${
                    scene.enabled
                      ? "border-red-300 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
                      : "border-purple-300 text-purple-600 hover:bg-purple-50 dark:border-purple-800 dark:text-purple-400 dark:hover:bg-purple-950"
                  }`}
                  disabled={disabled}
                  onClick={() => toggleEnabled(scene.scene_id)}
                >
                  {scene.enabled ? t(lang, "recipe_scene_remove") : t(lang, "recipe_scene_restore")}
                </button>
              </div>
            </div>

            {scene.vo_guide && (
              <div className="mt-2 text-sm">
                <span className="text-xs text-neutral-500">{t(lang, "recipe_vo_guide")}: </span>
                {scene.vo_guide}
              </div>
            )}
            {scene.on_screen_text && (
              <div className="text-xs text-neutral-500">
                {t(lang, "recipe_text_guide")}: {scene.on_screen_text}
              </div>
            )}
            {warning && (
              <div className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                {t(lang, "recipe_face_warning")}
              </div>
            )}
            {reframed && (
              <div className="mt-1 text-xs text-green-600 dark:text-green-400">{t(lang, "recipe_face_reframed")}</div>
            )}

            {expanded === scene.scene_id && (
              <div className="mt-3 flex flex-wrap items-end gap-3 rounded border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-900">
                <label className="text-xs text-neutral-600 dark:text-neutral-400">
                  {t(lang, "recipe_source")} start
                  <input
                    type="number"
                    step="0.5"
                    min={0}
                    max={recipe.project.source_duration ?? undefined}
                    value={scene.source_start}
                    disabled={disabled}
                    onChange={(e) => trim(scene.scene_id, "source_start", Number(e.target.value))}
                    className="mt-1 block w-28 rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-800"
                  />
                </label>
                <label className="text-xs text-neutral-600 dark:text-neutral-400">
                  {t(lang, "recipe_source")} end
                  <input
                    type="number"
                    step="0.5"
                    min={0}
                    max={recipe.project.source_duration ?? undefined}
                    value={scene.source_end}
                    disabled={disabled}
                    onChange={(e) => trim(scene.scene_id, "source_end", Number(e.target.value))}
                    className="mt-1 block w-28 rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-800"
                  />
                </label>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
