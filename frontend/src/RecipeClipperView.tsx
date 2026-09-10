import { useEffect, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import RecipeGenerateDialog from "./RecipeGenerateDialog";
import RecipeSummaryPanel from "./RecipeSummaryPanel";
import RecipeTimeline from "./RecipeTimeline";
import SocialKitPanel from "./SocialKitPanel";
import {
  analyzeRecipe,
  cancelJob,
  createProject,
  generateRecipeVideo,
  getRecipe,
  pollJob,
  saveRecipeTimeline,
  type Job,
  type Project,
  type Recipe,
  type RecipeAudioMode,
  type RecipeScene,
  type RecipeTargetDuration,
} from "./api";
import { t, type Language, type TranslationKey } from "./i18n";
import { setActiveJob } from "./jobStatusStore";
import { notify } from "./notify";
import type { AppSettings } from "./settings";

interface Props {
  settings: AppSettings;
  openProject: Project | null;
  /** The AI provider is configured once, in Settings -- this step only needs
   *  a way to send the user there when it has not been. */
  onOpenSettings: () => void;
}

const STEPS_KEY: TranslationKey[] = ["recipe_step_project", "recipe_step_analyze", "recipe_step_timeline"];
const TARGETS: { value: RecipeTargetDuration; key: TranslationKey }[] = [
  { value: "1min", key: "recipe_target_1min" },
  { value: "2min", key: "recipe_target_2min" },
  { value: "auto", key: "recipe_target_auto" },
];

function StepBar({ current, language }: { current: number; language: Language }) {
  return (
    <div className="mb-6 flex items-center">
      {STEPS_KEY.map((key, index) => {
        const step = index + 1;
        const done = step < current;
        const active = step === current;
        return (
          <div key={key} className="flex flex-1 items-center last:flex-none">
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                done
                  ? "bg-purple-600 text-white"
                  : active
                    ? "border-2 border-purple-600 text-purple-600 dark:text-purple-400"
                    : "border-2 border-neutral-300 text-neutral-400 dark:border-neutral-700 dark:text-neutral-500"
              }`}
            >
              {done ? "✓" : step}
            </div>
            <span
              className={`ml-2 text-sm ${
                active ? "font-medium text-neutral-900 dark:text-neutral-100" : "text-neutral-500"
              }`}
            >
              {t(language, key)}
            </span>
            {index < STEPS_KEY.length - 1 && <div className="mx-3 h-px flex-1 bg-neutral-300 dark:bg-neutral-700" />}
          </div>
        );
      })}
    </div>
  );
}

export default function RecipeClipperView({ settings, openProject, onOpenSettings }: Props) {
  const lang = settings.language;
  const [step, setStep] = useState(1);
  const [name, setName] = useState("Resep Baru");
  const [videoPath, setVideoPath] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const [project, setProject] = useState<Project | null>(null);

  const provider = settings.provider;
  const isProviderConfigured =
    provider.apiKey.trim() !== "" &&
    provider.model.trim() !== "" &&
    (provider.providerType !== "custom" || provider.baseUrl.trim() !== "");
  const [target, setTarget] = useState<RecipeTargetDuration>("1min");
  const [faceless, setFaceless] = useState(true);

  const [analyzeJob, setAnalyzeJob] = useState<Job | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [scenes, setScenes] = useState<RecipeScene[]>([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showGenerate, setShowGenerate] = useState(false);
  const [generateJob, setGenerateJob] = useState<Job | null>(null);
  const [generating, setGenerating] = useState(false);
  const [showSocialKit, setShowSocialKit] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const step1Valid = name.trim() !== "" && videoPath.trim() !== "";

  useEffect(() => {
    if (!openProject) return;
    setProject(openProject);
    setStep(2);
    getRecipe(openProject.id)
      .then((loaded) => {
        setRecipe(loaded);
        setScenes(loaded.scenes);
        if (loaded.scenes.length > 0) setStep(3);
      })
      .catch((e) => setError(String(e)));
  }, [openProject]);

  // Mirror running work into the sidebar, the same way AI Clipper does, so
  // switching menus does not hide that something is still processing.
  useEffect(() => {
    const running = analyzeJob && (analyzeJob.status === "queued" || analyzeJob.status === "running");
    setActiveJob(
      "recipe-analyze",
      running ? { label: t(lang, "recipe_analyzing"), progress: analyzeJob.progress, step: analyzeJob.current_step } : null,
    );
  }, [analyzeJob, lang]);

  useEffect(() => {
    const running = generateJob && (generateJob.status === "queued" || generateJob.status === "running");
    setActiveJob(
      "recipe-generate",
      running
        ? { label: t(lang, "recipe_generating"), progress: generateJob.progress, step: generateJob.current_step }
        : null,
    );
  }, [generateJob, lang]);

  useEffect(
    () => () => {
      setActiveJob("recipe-analyze", null);
      setActiveJob("recipe-generate", null);
    },
    [],
  );

  async function handleCreateProject() {
    setError(null);
    if (project) {
      setStep(2);
      return;
    }
    if (creatingProject) return;
    setCreatingProject(true);
    try {
      const created = await createProject(name, videoPath, "recipe");
      setProject(created);
      setStep(2);
    } catch (e) {
      setError(String(e));
    } finally {
      setCreatingProject(false);
    }
  }

  async function handleAnalyze() {
    if (!project) return;
    setError(null);
    setAnalyzing(true);
    try {
      const providerConfig = {
        provider_type: provider.providerType,
        model: provider.model,
        api_key: provider.apiKey,
        base_url: provider.baseUrl || undefined,
      };
      const job = await analyzeRecipe(project.id, providerConfig, target, faceless, settings.useGpu);
      setAnalyzeJob(job);
      const finished = await pollJob(job.id, setAnalyzeJob);
      if (finished.status === "completed") {
        const loaded = await getRecipe(project.id);
        setRecipe(loaded);
        setScenes(loaded.scenes);
        setStep(3);
        notify(t(lang, "recipe_detected"), loaded.recipe_name ?? "");
      } else if (finished.status === "failed") {
        notify(t(lang, "nav_recipe_clipper"), finished.error ?? "");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleSaveTimeline() {
    if (!project) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await saveRecipeTimeline(
        project.id,
        scenes.map((scene) => ({
          scene_id: scene.scene_id,
          source_start: scene.source_start,
          source_end: scene.source_end,
          enabled: scene.enabled,
        })),
      );
      setRecipe(updated);
      setScenes(updated.scenes);
      setDirty(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleGenerate(audioMode: RecipeAudioMode, volumePercent: number) {
    if (!project) return;
    setGenerating(true);
    setError(null);
    try {
      if (dirty) await handleSaveTimeline();
      const job = await generateRecipeVideo(
        project.id,
        audioMode,
        volumePercent,
        settings.outputFolder || undefined,
      );
      setGenerateJob(job);
      setShowGenerate(false);
      const finished = await pollJob(job.id, setGenerateJob);
      if (finished.status === "completed") {
        setRecipe(await getRecipe(project.id));
        notify(t(lang, "nav_recipe_clipper"), t(lang, "recipe_generate"));
      } else if (finished.status === "failed") {
        notify(t(lang, "nav_recipe_clipper"), finished.error ?? "");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  }

  const videoSrc = recipe?.clip?.video_path ? convertFileSrc(recipe.clip.video_path) : null;
  const enabledCount = scenes.filter((scene) => scene.enabled).length;
  const estimated = scenes.filter((s) => s.enabled).reduce((sum, s) => sum + (s.source_end - s.source_start), 0);

  return (
    <div>
      <h2 className="mb-1 text-lg font-semibold">🍳 {t(lang, "nav_recipe_clipper")}</h2>
      <p className="mb-5 max-w-2xl text-sm text-neutral-500">{t(lang, "recipe_intro")}</p>

      <StepBar current={step} language={lang} />

      {error && (
        <div className="mb-4 rounded bg-red-100 p-3 text-sm text-red-700 dark:bg-red-900 dark:text-red-100">{error}</div>
      )}

      {step === 1 && (
        <div className="max-w-md space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">
              {t(lang, "project_name")} <span className="text-red-500">*</span>
            </label>
            <input
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">
              {t(lang, "video_path")} <span className="text-red-500">*</span>
            </label>
            <div className="flex gap-2">
              <input
                className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
                value={videoPath}
                placeholder={t(lang, "choose_video_placeholder")}
                onChange={(e) => setVideoPath(e.target.value)}
              />
              <button
                className="whitespace-nowrap rounded border border-neutral-300 px-3 py-2 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                onClick={async () => {
                  const selected = await open({
                    multiple: false,
                    filters: [{ name: "Video", extensions: ["mp4", "mov", "mkv", "webm"] }],
                  });
                  if (typeof selected === "string") setVideoPath(selected);
                }}
              >
                {t(lang, "browse")}
              </button>
            </div>
          </div>
          <div className="flex justify-end pt-2">
            <button
              className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!step1Valid || creatingProject}
              onClick={handleCreateProject}
            >
              {creatingProject ? t(lang, "creating_project") : t(lang, "next")}
            </button>
          </div>
        </div>
      )}

      {step === 2 && project && (
        <div className="max-w-md space-y-3">
          <div className="text-sm text-neutral-500">
            {project.name} ({project.source_duration?.toFixed(0)}s, {project.source_resolution})
          </div>

          {!isProviderConfigured && (
            <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
              <div>{t(lang, "recipe_provider_missing")}</div>
              <button
                type="button"
                className="mt-2 rounded border border-amber-400 px-3 py-1.5 text-sm hover:bg-amber-100 dark:border-amber-700 dark:hover:bg-amber-900"
                onClick={onOpenSettings}
              >
                {t(lang, "recipe_open_settings")}
              </button>
            </div>
          )}

          <div>
            <div className="mb-1 text-xs font-medium text-neutral-600 dark:text-neutral-400">
              {t(lang, "recipe_target_duration")}
            </div>
            <div className="flex gap-2">
              {TARGETS.map((option) => (
                <button
                  key={option.value}
                  className={`rounded px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50 ${
                    target === option.value
                      ? "bg-purple-600 text-white"
                      : "border border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  }`}
                  disabled={analyzing}
                  onClick={() => setTarget(option.value)}
                >
                  {t(lang, option.key)}
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-neutral-500">{t(lang, "recipe_target_hint")}</p>
          </div>

          {isProviderConfigured && (
            <p className="text-xs text-neutral-500">
              {t(lang, "recipe_provider_note")}: {provider.providerType === "custom" ? "Custom" : provider.providerType}{" "}
              · {provider.model}{" "}
              <button type="button" className="text-purple-600 hover:underline dark:text-purple-400" onClick={onOpenSettings}>
                {t(lang, "recipe_change_in_settings")}
              </button>
            </p>
          )}

          <label className="flex items-start gap-2 rounded border border-neutral-200 p-3 text-sm dark:border-neutral-800">
            <input
              type="checkbox"
              className="mt-1"
              checked={faceless}
              disabled={analyzing}
              onChange={(e) => setFaceless(e.target.checked)}
            />
            <span>
              {t(lang, "recipe_faceless")}
              <span className="block text-xs text-neutral-500">{t(lang, "recipe_faceless_hint")}</span>
            </span>
          </label>

          {analyzeJob && (
            <div className="rounded border border-neutral-200 p-3 text-sm dark:border-neutral-800">
              <div>
                {analyzeJob.current_step ?? analyzeJob.status} ({analyzeJob.progress.toFixed(0)}%)
              </div>
              {analyzeJob.error && <div className="mt-1 text-red-500">{analyzeJob.error}</div>}
            </div>
          )}

          <div className="flex justify-between gap-2 pt-2">
            {analyzing ? (
              <button
                className="rounded border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
                onClick={async () => {
                  if (!analyzeJob) return;
                  try {
                    await cancelJob(analyzeJob.id);
                  } catch {
                    // best-effort: pollJob stops as soon as it sees a terminal status
                  }
                }}
              >
                {t(lang, "cancel")}
              </button>
            ) : (
              <button
                className="rounded border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                onClick={() => setStep(1)}
              >
                {t(lang, "back")}
              </button>
            )}
            <button
              className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={analyzing || !isProviderConfigured}
              onClick={scenes.length > 0 ? () => setStep(3) : handleAnalyze}
            >
              {analyzing ? t(lang, "recipe_analyzing") : scenes.length > 0 ? t(lang, "next") : t(lang, "recipe_analyze")}
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="max-w-3xl space-y-4">
          <div className="flex justify-start">
            <button
              className="rounded border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
              onClick={() => setStep(2)}
            >
              {t(lang, "back")}
            </button>
          </div>

          {!recipe || scenes.length === 0 ? (
            <p className="text-sm text-neutral-500">{t(lang, "recipe_empty_timeline")}</p>
          ) : (
            <>
              {recipe.visual_analysis === "unavailable" && (
                <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
                  <div className="font-medium">{t(lang, "recipe_visual_unavailable")}</div>
                  {recipe.warnings.map((warning) => (
                    <div key={warning} className="mt-1 text-xs">
                      {warning}
                    </div>
                  ))}
                </div>
              )}
              {recipe.visual_analysis === "ok" &&
                recipe.warnings.map((warning) => (
                  <div
                    key={warning}
                    className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
                  >
                    {warning}
                  </div>
                ))}

              <RecipeSummaryPanel lang={lang} recipe={recipe} />

              {videoSrc && (
                <video controls className="max-h-96 w-full rounded bg-black" src={videoSrc} key={videoSrc} />
              )}

              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm text-neutral-500">
                  {t(lang, "recipe_scenes_selected")}: {enabledCount} · {t(lang, "recipe_estimated_duration")}:{" "}
                  {Math.round(estimated)}s
                </div>
                <div className="flex gap-2">
                  <button
                    className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-800"
                    disabled={!dirty || saving || generating}
                    onClick={handleSaveTimeline}
                  >
                    {saving ? t(lang, "loading") : t(lang, "recipe_save_timeline")}
                  </button>
                  <button
                    className="rounded bg-purple-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-40"
                    disabled={generating || enabledCount === 0}
                    onClick={() => setShowGenerate(true)}
                  >
                    {generating ? t(lang, "recipe_generating") : t(lang, "recipe_generate")}
                  </button>
                  {recipe.clip && (
                    <button
                      className={`rounded border px-3 py-1.5 text-sm ${
                        showSocialKit
                          ? "border-purple-600 bg-purple-600 text-white hover:bg-purple-500"
                          : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                      }`}
                      onClick={() => setShowSocialKit((open) => !open)}
                    >
                      {t(lang, "social_kit")}
                    </button>
                  )}
                </div>
              </div>

              {generateJob && (generateJob.status === "running" || generateJob.status === "queued") && (
                <div className="rounded border border-neutral-200 p-3 text-sm dark:border-neutral-800">
                  {generateJob.current_step ?? generateJob.status} ({generateJob.progress.toFixed(0)}%)
                </div>
              )}
              {generateJob?.error && <div className="text-sm text-red-500">{generateJob.error}</div>}

              {showSocialKit && recipe.clip && (
                <SocialKitPanel
                  lang={lang}
                  clipId={recipe.clip.id}
                  provider={provider}
                  onClose={() => setShowSocialKit(false)}
                />
              )}

              <RecipeTimeline
                lang={lang}
                recipe={recipe}
                scenes={scenes}
                disabled={saving || generating}
                onChange={(next) => {
                  setScenes(next);
                  setDirty(true);
                }}
              />
            </>
          )}
        </div>
      )}

      {showGenerate && recipe && (
        <RecipeGenerateDialog
          lang={lang}
          estimatedDuration={estimated}
          faceless={recipe.faceless}
          busy={generating}
          onCancel={() => setShowGenerate(false)}
          onGenerate={handleGenerate}
        />
      )}
    </div>
  );
}
