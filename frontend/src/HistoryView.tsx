import { useEffect, useState } from "react";
import { listProjects, type Project } from "./api";
import { t, type Language } from "./i18n";

interface Props {
  language: Language;
  onOpenProject: (project: Project) => void;
}

export default function HistoryView({ language, onOpenProject }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="max-w-2xl space-y-4">
      <h2 className="text-lg font-semibold">{t(language, "nav_history")}</h2>

      {error && <div className="rounded bg-red-100 p-3 text-sm text-red-700 dark:bg-red-900 dark:text-red-100">{error}</div>}

      {projects.length === 0 && !error && <p className="text-sm text-neutral-500">{t(language, "history_empty")}</p>}

      {projects.map((p) => (
        <div key={p.id} className="flex items-center justify-between rounded border border-neutral-200 p-4 dark:border-neutral-800">
          <div>
            <div className="font-medium">{p.name}</div>
            <div className="text-xs text-neutral-500">
              {t(language, "history_created")}: {new Date(p.created_at).toLocaleString()} -- {t(language, "history_duration")}:{" "}
              {p.source_duration?.toFixed(0)}s -- {t(language, "history_status")}: {p.status}
            </div>
          </div>
          <button
            className="rounded bg-neutral-100 px-3 py-1.5 text-sm hover:bg-neutral-200 dark:bg-neutral-800 dark:hover:bg-neutral-700"
            onClick={() => onOpenProject(p)}
          >
            {t(language, "history_open")}
          </button>
        </div>
      ))}
    </div>
  );
}
