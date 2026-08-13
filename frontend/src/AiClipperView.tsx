import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  analyzeProject,
  cancelJob,
  createProject,
  generateClip,
  listClips,
  pollJob,
  type Clip,
  type Job,
  type Project,
} from "./api";
import ClipResultCard from "./ClipResultCard";
import { t, type Language } from "./i18n";
import { notify } from "./notify";
import { setActiveJob } from "./jobStatusStore";
import ProviderConfigFields from "./ProviderConfigFields";
import type { AppSettings } from "./settings";

function useEtaSeconds(job: Job | null): number | null {
  const [eta, setEta] = useState<number | null>(null);

  useEffect(() => {
    if (!job || job.status !== "running" || !job.started_at || job.progress <= 2) {
      setEta(null);
      return;
    }
    const elapsedMs = Date.now() - new Date(job.started_at).getTime();
    const remaining = (elapsedMs / job.progress) * (100 - job.progress);
    setEta(Math.max(0, Math.round(remaining / 1000)));
  }, [job]);

  return eta;
}

function formatSeconds(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

const STEPS_KEY = ["step_project", "step_analyze", "step_clips"] as const;
const CLIP_COUNT_OPTIONS = ["auto", "3", "5", "10"] as const;

function Label({ text, required }: { text: string; required?: boolean }) {
  return (
    <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">
      {text} {required && <span className="text-red-500">*</span>}
    </label>
  );
}

function StepBar({ current, language }: { current: number; language: Language }) {
  return (
    <div className="mb-6 flex items-center">
      {STEPS_KEY.map((key, i) => {
        const stepNum = i + 1;
        const done = stepNum < current;
        const active = stepNum === current;
        return (
          <div key={key} className="flex flex-1 items-center last:flex-none">
            <div className="flex items-center gap-2">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                  done
                    ? "bg-purple-600 text-white"
                    : active
                      ? "border-2 border-purple-600 text-purple-600 dark:text-purple-400"
                      : "border-2 border-neutral-300 text-neutral-400 dark:border-neutral-700 dark:text-neutral-500"
                }`}
              >
                {done ? "✓" : stepNum}
              </div>
              <span className={`text-sm ${active ? "font-medium text-neutral-900 dark:text-neutral-100" : "text-neutral-500"}`}>
                {t(language, key)}
              </span>
            </div>
            {stepNum < STEPS_KEY.length && <div className="mx-3 h-px flex-1 bg-neutral-300 dark:bg-neutral-700" />}
          </div>
        );
      })}
    </div>
  );
}

interface Props {
  settings: AppSettings;
  onSettingsChange: (next: AppSettings) => void;
  openProject: Project | null;
}

export default function AiClipperView({ settings, onSettingsChange, openProject }: Props) {
  const lang = settings.language;
  const [step, setStep] = useState(1);

  const [name, setName] = useState("My Project");
  const [videoPath, setVideoPath] = useState("");

  // Provider config lives in `settings` (not local state) so it's set once --
  // here or in Settings -- and reused everywhere, instead of having to be
  // re-typed every time this view is opened.
  const provider = settings.provider;
  function setProvider(next: AppSettings["provider"]) {
    onSettingsChange({ ...settings, provider: next });
  }
  const isProviderConfigured =
    provider.apiKey.trim() !== "" && provider.model.trim() !== "" && (provider.providerType !== "custom" || provider.baseUrl.trim() !== "");
  // Collapsed into a one-line summary when a provider is already configured
  // (usually from Settings) so this step doesn't re-ask for it every time --
  // "Ubah" expands it back out for editing.
  const [editingProvider, setEditingProvider] = useState(!isProviderConfigured);
  const [clipCountOption, setClipCountOption] = useState<(typeof CLIP_COUNT_OPTIONS)[number]>("auto");

  const [project, setProject] = useState<Project | null>(null);
  const [analyzeJob, setAnalyzeJob] = useState<Job | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [clips, setClips] = useState<Clip[]>([]);
  const [generateJobs, setGenerateJobs] = useState<Record<string, Job>>({});
  const [error, setError] = useState<string | null>(null);
  const analyzeEta = useEtaSeconds(analyzeJob);

  useEffect(() => {
    if (openProject) {
      setProject(openProject);
      setStep(2);
      listClips(openProject.id)
        .then((loaded) => {
          setClips(loaded);
          if (loaded.length > 0) setStep(3);
        })
        .catch((e) => setError(String(e)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openProject]);

  // Mirror the currently running job(s) into a global store so other views (e.g. the
  // sidebar) can show that something is still processing even while this view is hidden.
  useEffect(() => {
    if (analyzeJob && (analyzeJob.status === "queued" || analyzeJob.status === "running")) {
      setActiveJob("analyze", {
        label: t(lang, "analyzing"),
        progress: analyzeJob.progress,
        step: analyzeJob.current_step,
      });
    } else {
      setActiveJob("analyze", null);
    }
  }, [analyzeJob, lang]);

  useEffect(() => {
    for (const [clipId, job] of Object.entries(generateJobs)) {
      const key = `generate-${clipId}`;
      if (job.status === "queued" || job.status === "running") {
        setActiveJob(key, { label: t(lang, "generating"), progress: job.progress, step: job.current_step });
      } else {
        setActiveJob(key, null);
      }
    }
  }, [generateJobs, lang]);

  useEffect(() => {
    return () => {
      setActiveJob("analyze", null);
      for (const clipId of Object.keys(generateJobs)) setActiveJob(`generate-${clipId}`, null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const step1Valid = name.trim() !== "" && videoPath.trim() !== "";
  const step2Valid =
    provider.model.trim() !== "" && provider.apiKey.trim() !== "" && (provider.providerType !== "custom" || provider.baseUrl.trim() !== "");

  async function handleBrowseVideo() {
    setError(null);
    try {
      const path = await open({
        multiple: false,
        directory: false,
        filters: [{ name: "Video", extensions: ["mp4", "mov", "mkv", "webm"] }],
      });
      if (typeof path === "string") setVideoPath(path);
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleNextFromProjectStep() {
    setError(null);
    if (project) {
      setStep(2);
      return;
    }
    try {
      const p = await createProject(name, videoPath);
      setProject(p);
      setStep(2);
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAnalyzeOrNext() {
    if (!project) return;
    if (clips.length > 0) {
      setStep(3);
      return;
    }
    setError(null);
    setAnalyzing(true);
    try {
      const numClips = clipCountOption === "auto" ? null : Number(clipCountOption);
      const providerConfig = {
        provider_type: provider.providerType,
        model: provider.model,
        api_key: provider.apiKey,
        base_url: provider.baseUrl || undefined,
      };
      const job = await analyzeProject(project.id, providerConfig, numClips, settings.useGpu);
      setAnalyzeJob(job);
      const finished = await pollJob(job.id, setAnalyzeJob);
      if (finished.status === "completed") {
        const loadedClips = await listClips(project.id);
        setClips(loadedClips);
        setStep(3);
        notify(
          t(lang, "notif_analyze_done_title"),
          t(lang, "notif_analyze_done_body").replace("{n}", String(loadedClips.length)),
        );
      } else if (finished.status === "failed") {
        notify(t(lang, "notif_analyze_failed_title"), finished.error ?? "");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleCancelAnalyze() {
    if (analyzeJob) {
      try {
        await cancelJob(analyzeJob.id);
      } catch {
        // best-effort -- pollJob's loop will still stop once it sees a terminal status
      }
    }
  }

  async function handleGenerate(clipId: string, includeSubtitle: boolean) {
    setError(null);
    try {
      const job = await generateClip(clipId, includeSubtitle, settings.outputFolder || undefined);
      setGenerateJobs((prev) => ({ ...prev, [clipId]: job }));
      const finished = await pollJob(job.id, (j) => setGenerateJobs((prev) => ({ ...prev, [clipId]: j })));
      if (project) setClips(await listClips(project.id));
      if (finished.status === "completed") {
        notify(t(lang, "notif_generate_done_title"), "");
      } else if (finished.status === "failed") {
        notify(t(lang, "notif_generate_failed_title"), finished.error ?? "");
      }
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div>
      <StepBar current={step} language={lang} />

      {error && <div className="mb-4 rounded bg-red-100 p-3 text-sm text-red-700 dark:bg-red-900 dark:text-red-100">{error}</div>}

      {step === 1 && (
        <div className="max-w-md space-y-3">
          <div>
            <Label text={t(lang, "project_name")} required />
            <input
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <Label text={t(lang, "video_path")} required />
            <div className="flex gap-2">
              <input
                className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
                placeholder={t(lang, "choose_video_placeholder")}
                value={videoPath}
                onChange={(e) => setVideoPath(e.target.value)}
              />
              <button
                className="whitespace-nowrap rounded border border-neutral-300 px-3 py-2 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                onClick={handleBrowseVideo}
              >
                {t(lang, "browse")}
              </button>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!step1Valid}
              onClick={handleNextFromProjectStep}
            >
              {t(lang, "next")}
            </button>
          </div>
        </div>
      )}

      {step === 2 && project && (
        <div className="max-w-md space-y-3">
          <div className="text-sm text-neutral-500">
            {project.name} ({project.source_duration?.toFixed(0)}s, {project.source_resolution})
          </div>

          {isProviderConfigured && !editingProvider ? (
            <div className="flex items-center justify-between rounded border border-green-200 bg-green-50 p-3 text-sm dark:border-green-900 dark:bg-green-950">
              <div>
                <div className="font-medium text-green-700 dark:text-green-400">✓ {t(lang, "provider_configured")}</div>
                <div className="text-xs text-neutral-500">
                  {provider.providerType === "custom" ? "Custom" : provider.providerType} · {provider.model}
                </div>
              </div>
              <button
                type="button"
                className="text-sm text-purple-600 hover:underline disabled:opacity-50 dark:text-purple-400"
                onClick={() => setEditingProvider(true)}
                disabled={analyzing}
              >
                {t(lang, "change_provider")}
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {isProviderConfigured && (
                <div className="text-right">
                  <button
                    type="button"
                    className="text-xs text-neutral-500 hover:underline"
                    onClick={() => setEditingProvider(false)}
                    disabled={analyzing}
                  >
                    ▲ {t(lang, "hide_provider_form")}
                  </button>
                </div>
              )}
              <ProviderConfigFields lang={lang} value={provider} disabled={analyzing} onChange={setProvider} />
            </div>
          )}

          <div>
            <Label text={t(lang, "num_clips")} />
            <div className="flex gap-2">
              {CLIP_COUNT_OPTIONS.map((opt) => (
                <button
                  key={opt}
                  disabled={analyzing}
                  className={`rounded px-3 py-1.5 text-sm capitalize disabled:cursor-not-allowed disabled:opacity-50 ${
                    clipCountOption === opt
                      ? "bg-purple-600 text-white"
                      : "border border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  }`}
                  onClick={() => setClipCountOption(opt)}
                >
                  {opt}
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-neutral-500">{t(lang, "num_clips_hint")}</p>
          </div>

          {analyzeJob && (
            <div className="text-sm text-neutral-500">
              {analyzeJob.status}: {analyzeJob.current_step ?? ""} ({analyzeJob.progress.toFixed(0)}%)
              {analyzeJob.status === "running" && (
                <div>
                  {t(lang, "eta_remaining")}: {analyzeEta === null ? t(lang, "eta_calculating") : `~${formatSeconds(analyzeEta)}`}
                </div>
              )}
              {analyzeJob.error && <div className="text-red-500">{analyzeJob.error}</div>}
            </div>
          )}

          <div className="flex justify-between gap-2 pt-2">
            {analyzing ? (
              <button
                className="rounded border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
                onClick={handleCancelAnalyze}
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
              disabled={!step2Valid || analyzing}
              onClick={handleAnalyzeOrNext}
            >
              {analyzing ? t(lang, "analyzing") : clips.length > 0 ? t(lang, "next") : t(lang, "analyze")}
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <div className="flex justify-start">
            <button
              className="rounded border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
              onClick={() => setStep(2)}
            >
              {t(lang, "back")}
            </button>
          </div>

          {clips.map((clip) => (
            <ClipResultCard
              key={clip.id}
              lang={lang}
              clip={clip}
              genJob={generateJobs[clip.id]}
              provider={provider}
              onGenerate={handleGenerate}
            />
          ))}
        </div>
      )}
    </div>
  );
}
