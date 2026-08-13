import { useEffect, useState } from "react";
import { listJobs, listProjects, type Job, type Project } from "./api";
import { t, type Language, type TranslationKey } from "./i18n";

interface Props {
  language: Language;
  onOpenProject: (project: Project) => void;
}

function jobTypeKey(type: string): TranslationKey {
  return type === "generate_clip" ? "job_type_generate_clip" : "job_type_analyze_video";
}

function jobStatusKey(status: string): TranslationKey {
  switch (status) {
    case "running":
      return "job_status_running";
    case "completed":
      return "job_status_completed";
    case "failed":
      return "job_status_failed";
    case "cancelled":
      return "job_status_cancelled";
    default:
      return "job_status_queued";
  }
}

export default function HistoryView({ language, onOpenProject }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [latestJobs, setLatestJobs] = useState<Record<string, Job | null>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(async (loaded) => {
        setProjects(loaded);
        const entries = await Promise.all(
          loaded.map(async (p): Promise<[string, Job | null]> => {
            try {
              const jobs = await listJobs(p.id);
              return [p.id, jobs[0] ?? null];
            } catch {
              return [p.id, null];
            }
          }),
        );
        setLatestJobs(Object.fromEntries(entries));
      })
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="max-w-2xl space-y-4">
      <h2 className="text-lg font-semibold">{t(language, "nav_history")}</h2>

      {error && <div className="rounded bg-red-100 p-3 text-sm text-red-700 dark:bg-red-900 dark:text-red-100">{error}</div>}

      {projects.length === 0 && !error && <p className="text-sm text-neutral-500">{t(language, "history_empty")}</p>}

      {projects.map((p) => {
        const job = latestJobs[p.id];
        const isNegative = job?.status === "failed" || job?.status === "cancelled";
        return (
          <div key={p.id} className="rounded border border-neutral-200 p-4 dark:border-neutral-800">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-neutral-500">
                  {t(language, "history_created")}: {new Date(p.created_at).toLocaleString()} -- {t(language, "history_duration")}:{" "}
                  {p.source_duration?.toFixed(0)}s
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                {isNegative && (
                  <button
                    className="whitespace-nowrap rounded border border-purple-300 px-3 py-1.5 text-sm text-purple-600 hover:bg-purple-50 dark:border-purple-800 dark:text-purple-400 dark:hover:bg-purple-950"
                    onClick={() => onOpenProject(p)}
                  >
                    ↻ {t(language, "history_retry")}
                  </button>
                )}
                <button
                  className="whitespace-nowrap rounded bg-neutral-100 px-3 py-1.5 text-sm hover:bg-neutral-200 dark:bg-neutral-800 dark:hover:bg-neutral-700"
                  onClick={() => onOpenProject(p)}
                >
                  {t(language, "history_open")}
                </button>
              </div>
            </div>
            {job && (
              <div className={`mt-2 text-xs ${isNegative ? "text-red-600 dark:text-red-400" : "text-neutral-500"}`}>
                {t(language, jobTypeKey(job.type))}: {t(language, jobStatusKey(job.status))}
                {job.status === "running" && ` (${job.progress.toFixed(0)}%)`}
                {isNegative && job.error && ` -- ${job.error}`}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
