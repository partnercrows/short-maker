import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  analyzeProject,
  createProject,
  generateClip,
  listClips,
  pollJob,
  type Clip,
  type Job,
  type Project,
} from "./api";

const STEPS = ["Project", "Analyze", "Clips"] as const;
const PROVIDERS = ["gemini", "openai", "deepseek", "groq", "openrouter", "xai", "mistral", "custom"] as const;
const CLIP_COUNT_OPTIONS = ["auto", "3", "5", "10"] as const;

function Label({ text, required }: { text: string; required?: boolean }) {
  return (
    <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">
      {text} {required && <span className="text-red-500">*</span>}
    </label>
  );
}

function StepBar({ current }: { current: number }) {
  return (
    <div className="mb-6 flex items-center">
      {STEPS.map((label, i) => {
        const stepNum = i + 1;
        const done = stepNum < current;
        const active = stepNum === current;
        return (
          <div key={label} className="flex flex-1 items-center last:flex-none">
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
              <span
                className={`text-sm ${active ? "font-medium text-neutral-900 dark:text-neutral-100" : "text-neutral-500"}`}
              >
                {label}
              </span>
            </div>
            {stepNum < STEPS.length && <div className="mx-3 h-px flex-1 bg-neutral-300 dark:bg-neutral-700" />}
          </div>
        );
      })}
    </div>
  );
}

function ThemeToggle({ theme, onToggle }: { theme: "light" | "dark"; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-600 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800"
      title="Toggle light/dark theme"
    >
      {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
    </button>
  );
}

function parseAnalysis(clip: Clip) {
  if (!clip.analysis_json) return null;
  try {
    const a = JSON.parse(clip.analysis_json);
    return {
      reason: a.reason as string,
      suggestedTitle: a.suggested_title as string,
      hook: a.hook_score as number,
      curiosity: a.curiosity_score as number,
      emotion: a.emotion_score as number,
      information: a.information_score as number,
    };
  } catch {
    return null;
  }
}

function App() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("theme", theme);
  }, [theme]);

  const [step, setStep] = useState(1);

  const [name, setName] = useState("My Project");
  const [videoPath, setVideoPath] = useState("");

  const [providerType, setProviderType] = useState<(typeof PROVIDERS)[number]>("gemini");
  const [model, setModel] = useState("gemini-flash-latest");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [clipCountOption, setClipCountOption] = useState<(typeof CLIP_COUNT_OPTIONS)[number]>("auto");

  const [project, setProject] = useState<Project | null>(null);
  const [analyzeJob, setAnalyzeJob] = useState<Job | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [clips, setClips] = useState<Clip[]>([]);
  const [generateJobs, setGenerateJobs] = useState<Record<string, Job>>({});
  const [error, setError] = useState<string | null>(null);

  const step1Valid = name.trim() !== "" && videoPath.trim() !== "";
  const step2Valid =
    model.trim() !== "" && apiKey.trim() !== "" && (providerType !== "custom" || baseUrl.trim() !== "");

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
      const provider = { provider_type: providerType, model, api_key: apiKey, base_url: baseUrl || undefined };
      const job = await analyzeProject(project.id, provider, numClips);
      setAnalyzeJob(job);
      const finished = await pollJob(job.id, setAnalyzeJob);
      if (finished.status === "completed") {
        setClips(await listClips(project.id));
        setStep(3);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleGenerate(clipId: string, includeSubtitle: boolean) {
    setError(null);
    try {
      const job = await generateClip(clipId, includeSubtitle);
      setGenerateJobs((prev) => ({ ...prev, [clipId]: job }));
      await pollJob(job.id, (j) => setGenerateJobs((prev) => ({ ...prev, [clipId]: j })));
      if (project) setClips(await listClips(project.id));
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="min-h-screen bg-white p-6 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Short Maker</h1>
        <ThemeToggle theme={theme} onToggle={() => setTheme(theme === "dark" ? "light" : "dark")} />
      </div>

      <StepBar current={step} />

      {error && <div className="mb-4 rounded bg-red-100 p-3 text-sm text-red-700 dark:bg-red-900 dark:text-red-100">{error}</div>}

      {step === 1 && (
        <div className="max-w-md space-y-3">
          <div>
            <Label text="Project name" required />
            <input
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <Label text="Local video path" required />
            <div className="flex gap-2">
              <input
                className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
                placeholder="Choose a video file..."
                value={videoPath}
                onChange={(e) => setVideoPath(e.target.value)}
              />
              <button
                className="whitespace-nowrap rounded border border-neutral-300 px-3 py-2 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                onClick={handleBrowseVideo}
              >
                Browse...
              </button>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!step1Valid}
              onClick={handleNextFromProjectStep}
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {step === 2 && project && (
        <div className="max-w-md space-y-3">
          <div className="text-sm text-neutral-500">
            Project: <span className="text-neutral-900 dark:text-neutral-100">{project.name}</span> (
            {project.source_duration?.toFixed(0)}s, {project.source_resolution})
          </div>

          <div>
            <Label text="Provider" required />
            <select
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
              value={providerType}
              onChange={(e) => setProviderType(e.target.value as (typeof PROVIDERS)[number])}
            >
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p === "custom" ? "Custom (OpenAI-compatible)" : p}
                </option>
              ))}
            </select>
          </div>

          <div>
            <Label text="Model" required />
            <input
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </div>

          <div>
            <Label text="API key" required />
            <input
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

          <div>
            <Label text="Base URL" required={providerType === "custom"} />
            <input
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
              placeholder={providerType === "custom" ? "https://your-endpoint/v1" : "Leave blank to use the provider's default"}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>

          <div>
            <Label text="Number of clips" />
            <div className="flex gap-2">
              {CLIP_COUNT_OPTIONS.map((opt) => (
                <button
                  key={opt}
                  className={`rounded px-3 py-1.5 text-sm capitalize ${
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
            <p className="mt-1 text-xs text-neutral-500">
              "Auto" lets the AI decide how many clips are actually worth making from this video.
            </p>
          </div>

          {analyzeJob && (
            <div className="text-sm text-neutral-500">
              Job {analyzeJob.status}: {analyzeJob.current_step ?? ""} ({analyzeJob.progress.toFixed(0)}%)
              {analyzeJob.error && <div className="text-red-500">{analyzeJob.error}</div>}
            </div>
          )}

          <div className="flex justify-between gap-2 pt-2">
            <button
              className="rounded border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
              onClick={() => setStep(1)}
            >
              ← Back
            </button>
            <button
              className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!step2Valid || analyzing}
              onClick={handleAnalyzeOrNext}
            >
              {analyzing ? "Analyzing..." : clips.length > 0 ? "Next →" : "Analyze →"}
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
              ← Back
            </button>
          </div>

          {clips.map((clip) => {
            const analysis = parseAnalysis(clip);
            const genJob = generateJobs[clip.id];
            return (
              <div key={clip.id} className="max-w-xl rounded border border-neutral-200 p-4 dark:border-neutral-800">
                <div className="flex justify-between">
                  <span className="font-medium">{analysis?.suggestedTitle ?? "(untitled)"}</span>
                  <span className="text-purple-600 dark:text-purple-400">{clip.score?.toFixed(0)}/100</span>
                </div>
                <div className="text-xs text-neutral-500">
                  {clip.start_time.toFixed(1)}s - {clip.end_time.toFixed(1)}s ({clip.duration.toFixed(1)}s) -- status:{" "}
                  {clip.status}
                </div>
                {analysis && (
                  <>
                    <p className="mt-2 text-sm text-neutral-700 dark:text-neutral-300">{analysis.reason}</p>
                    <div className="mt-1 text-xs text-neutral-500">
                      Hook {analysis.hook} / Curiosity {analysis.curiosity} / Emotion {analysis.emotion} / Info{" "}
                      {analysis.information}
                    </div>
                  </>
                )}
                <div className="mt-3 flex items-center gap-2">
                  <button
                    className="rounded bg-neutral-100 px-3 py-1.5 text-sm hover:bg-neutral-200 dark:bg-neutral-800 dark:hover:bg-neutral-700"
                    onClick={() => handleGenerate(clip.id, true)}
                    disabled={genJob?.status === "queued" || genJob?.status === "running"}
                  >
                    Generate (with subtitles)
                  </button>
                  {genJob && (
                    <span className="text-xs text-neutral-500">
                      {genJob.status}: {genJob.current_step ?? ""} ({genJob.progress.toFixed(0)}%)
                    </span>
                  )}
                </div>
                {clip.video_path && <div className="mt-2 break-all text-xs text-green-600 dark:text-green-400">{clip.video_path}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default App;
