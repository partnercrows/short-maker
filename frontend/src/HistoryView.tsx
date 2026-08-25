import { useEffect, useState } from "react";
import { deleteAllProjects, deleteProject, listJobs, listProjects, type Job, type Project } from "./api";
import { t, type Language, type TranslationKey } from "./i18n";

interface Props {
  language: Language;
  onOpenProject: (project: Project) => void;
  /** Lets the shell drop a project it currently has open in the clipper --
   *  its files no longer exist, so continuing to show its clips would fail. */
  onProjectsDeleted?: (deleted: string[] | "all") => void;
}

/** What's pending confirmation: one project, or the whole history. */
type PendingDelete = { kind: "project"; project: Project } | { kind: "all" };

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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

function ConfirmDeleteDialog({
  language,
  pending,
  projectCount,
  freedBytes,
  deleting,
  onCancel,
  onConfirm,
}: {
  language: Language;
  pending: PendingDelete;
  projectCount: number;
  freedBytes: number;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-5 shadow-xl dark:border-neutral-800 dark:bg-neutral-900"
      >
        <h3 className="text-base font-semibold text-red-600 dark:text-red-400">{t(language, "history_delete_confirm_title")}</h3>
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
          {t(language, pending.kind === "all" ? "history_delete_all_confirm_body" : "history_delete_confirm_body")}
        </p>
        <div className="mt-3 rounded bg-neutral-100 p-3 text-sm dark:bg-neutral-800">
          <div className="font-medium">
            {pending.kind === "all" ? `${projectCount} ${t(language, "nav_history").toLowerCase()}` : pending.project.name}
          </div>
          <div className="text-xs text-neutral-500">
            {t(language, "history_delete_frees")}: {formatBytes(freedBytes)}
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
            onClick={onCancel}
            disabled={deleting}
          >
            {t(language, "history_cancel")}
          </button>
          <button
            className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
            onClick={onConfirm}
            disabled={deleting}
          >
            {deleting ? t(language, "history_deleting") : t(language, "history_delete")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function HistoryView({ language, onOpenProject, onProjectsDeleted }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [latestJobs, setLatestJobs] = useState<Record<string, Job | null>>({});
  const [error, setError] = useState<string | null>(null);
  const [manageMode, setManageMode] = useState(false);
  const [pending, setPending] = useState<PendingDelete | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [freedNotice, setFreedNotice] = useState<{ bytes: number; partial: boolean } | null>(null);

  function load() {
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
  }

  useEffect(load, []);

  const totalBytes = projects.reduce((sum, p) => sum + (p.storage_bytes ?? 0), 0);
  const pendingBytes = pending === null ? 0 : pending.kind === "all" ? totalBytes : (pending.project.storage_bytes ?? 0);

  async function confirmDelete() {
    if (!pending) return;
    setDeleting(true);
    setError(null);
    try {
      const result = pending.kind === "all" ? await deleteAllProjects() : await deleteProject(pending.project.id);
      setFreedNotice({ bytes: result.freed_bytes, partial: result.failed_paths.length > 0 });
      onProjectsDeleted?.(pending.kind === "all" ? "all" : [pending.project.id]);
      setPending(null);
      load();
    } catch (e) {
      setError(String(e));
      setPending(null);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{t(language, "nav_history")}</h2>
        {projects.length > 0 && (
          <div className="flex gap-2">
            {manageMode && (
              <button
                className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500"
                onClick={() => setPending({ kind: "all" })}
              >
                🗑 {t(language, "history_delete_all")}
              </button>
            )}
            <button
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
              onClick={() => setManageMode((on) => !on)}
            >
              {manageMode ? t(language, "history_manage_done") : `🗑 ${t(language, "history_manage")}`}
            </button>
          </div>
        )}
      </div>

      {projects.length > 0 && (
        <p className="text-xs text-neutral-500">
          {t(language, "history_total_storage")}: {formatBytes(totalBytes)}
        </p>
      )}

      {error && <div className="rounded bg-red-100 p-3 text-sm text-red-700 dark:bg-red-900 dark:text-red-100">{error}</div>}

      {freedNotice && (
        <div className="rounded bg-green-100 p-3 text-sm text-green-800 dark:bg-green-900 dark:text-green-100">
          {t(language, "history_deleted_freed")}: {formatBytes(freedNotice.bytes)}
          {freedNotice.partial && <div className="mt-1 text-xs">{t(language, "history_delete_partial")}</div>}
        </div>
      )}

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
                  {p.source_duration?.toFixed(0)}s -- {t(language, "history_storage")}: {formatBytes(p.storage_bytes ?? 0)}
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                {manageMode ? (
                  <button
                    className="whitespace-nowrap rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
                    onClick={() => setPending({ kind: "project", project: p })}
                  >
                    🗑 {t(language, "history_delete")}
                  </button>
                ) : (
                  <>
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
                  </>
                )}
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

      {pending && (
        <ConfirmDeleteDialog
          language={language}
          pending={pending}
          projectCount={projects.length}
          freedBytes={pendingBytes}
          deleting={deleting}
          onCancel={() => setPending(null)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  );
}
