import { useState } from "react";
import type { Recipe } from "./api";
import { t, type Language } from "./i18n";

interface Props {
  lang: Language;
  recipe: Recipe;
}

function CopyButton({ lang, text, label }: { lang: Language; text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="rounded border border-purple-300 px-3 py-1.5 text-sm text-purple-600 hover:bg-purple-50 disabled:opacity-40 dark:border-purple-800 dark:text-purple-400 dark:hover:bg-purple-950"
      disabled={!text}
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? t(lang, "copied") : label}
    </button>
  );
}

/** What the AI understood, and the two things the creator takes away with
 *  them: the voice-over script they will read, and the on-screen text they
 *  will typeset elsewhere (PRD S30, S33, S34). */
export default function RecipeSummaryPanel({ lang, recipe }: Props) {
  const [showScript, setShowScript] = useState(false);

  return (
    <div className="rounded border border-purple-200 bg-purple-50/50 p-4 dark:border-purple-900 dark:bg-purple-950/30">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-xs text-neutral-500">{t(lang, "recipe_detected")}</div>
          <div className="text-base font-semibold">{recipe.recipe_name ?? "-"}</div>
        </div>
        <div className="text-right text-xs text-neutral-500">
          {t(lang, "recipe_scenes_selected")}: {recipe.scenes.filter((s) => s.enabled).length}
          <div>
            {t(lang, "recipe_estimated_duration")}: {Math.round(recipe.estimated_duration)}s
          </div>
        </div>
      </div>

      {recipe.main_ingredient && (
        <div className="mt-2 text-sm">
          <span className="text-xs text-neutral-500">{t(lang, "recipe_main_ingredient")}: </span>
          {recipe.main_ingredient}
        </div>
      )}

      {recipe.ingredients.length > 0 && (
        <div className="mt-2">
          <div className="text-xs text-neutral-500">{t(lang, "recipe_ingredients")}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {recipe.ingredients.map((ingredient) => (
              <span
                key={ingredient.name}
                className="rounded bg-white px-2 py-0.5 text-xs text-purple-600 dark:bg-neutral-900 dark:text-purple-400"
              >
                {ingredient.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {recipe.possible_ingredients.length > 0 && (
        <div className="mt-2">
          {/* Shown apart from the confident list on purpose: the AI is not
              allowed to state these as fact (PRD S8). */}
          <div className="text-xs text-neutral-500">{t(lang, "recipe_possible_ingredients")}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {recipe.possible_ingredients.map((name) => (
              <span
                key={name}
                className="rounded border border-dashed border-neutral-300 px-2 py-0.5 text-xs text-neutral-500 dark:border-neutral-700"
              >
                {name}?
              </span>
            ))}
          </div>
        </div>
      )}

      {recipe.cooking_flow.length > 0 && (
        <div className="mt-2 text-xs text-neutral-500">
          {t(lang, "recipe_cooking_flow")}: {recipe.cooking_flow.join(" → ")}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <CopyButton lang={lang} text={recipe.vo_script} label={`🎙 ${t(lang, "recipe_copy_vo")}`} />
        <CopyButton lang={lang} text={recipe.text_guide} label={`📝 ${t(lang, "recipe_copy_text_guide")}`} />
        <button
          className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
          onClick={() => setShowScript((open) => !open)}
        >
          {showScript ? t(lang, "close") : t(lang, "recipe_vo_script")}
        </button>
      </div>

      {showScript && (
        <pre className="mt-3 max-h-72 overflow-y-auto whitespace-pre-wrap rounded border border-neutral-200 bg-white p-3 text-xs dark:border-neutral-800 dark:bg-neutral-900">
          {recipe.vo_script}
          {"\n\n"}
          {recipe.text_guide}
        </pre>
      )}

      <p className="mt-3 text-xs text-neutral-500">{t(lang, "recipe_no_subtitle_note")}</p>
    </div>
  );
}
