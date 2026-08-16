import { useEffect, useState, useSyncExternalStore } from "react";
import { getVersion } from "@tauri-apps/api/app";
import { t, type Language } from "./i18n";
import { getActiveJobs, subscribeActiveJobs } from "./jobStatusStore";

export type View = "clipper" | "history" | "youtube_download" | "settings";

interface Props {
  view: View;
  onNavigate: (view: View) => void;
  language: Language;
}

function NavButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full rounded px-3 py-2 text-left text-sm ${
        active
          ? "bg-purple-600 text-white"
          : "text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
      }`}
    >
      {label}
    </button>
  );
}

export default function Sidebar({ view, onNavigate, language }: Props) {
  const [version, setVersion] = useState("0.1.0");
  const activeJobs = useSyncExternalStore(subscribeActiveJobs, getActiveJobs);

  useEffect(() => {
    getVersion()
      .then(setVersion)
      .catch(() => {});
  }, []);

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-neutral-200 bg-neutral-50 p-4 dark:border-neutral-800 dark:bg-neutral-900">
      <h1 className="mb-6 text-lg font-semibold text-neutral-900 dark:text-neutral-100">Short Maker</h1>

      <nav className="flex flex-col gap-1">
        <NavButton active={view === "clipper"} label={t(language, "nav_ai_clipper")} onClick={() => onNavigate("clipper")} />
        <NavButton active={view === "history"} label={t(language, "nav_history")} onClick={() => onNavigate("history")} />
        <NavButton
          active={view === "youtube_download"}
          label={t(language, "nav_youtube_download")}
          onClick={() => onNavigate("youtube_download")}
        />
      </nav>

      {activeJobs.length > 0 && (
        <button
          onClick={() => onNavigate("clipper")}
          className="mt-3 rounded border border-purple-300 bg-purple-50 p-2 text-left text-xs text-purple-700 hover:bg-purple-100 dark:border-purple-800 dark:bg-purple-950 dark:text-purple-300"
        >
          <div className="mb-1 flex items-center gap-1.5 font-medium">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-purple-500" />
            {t(language, "background_jobs_running")}
          </div>
          {activeJobs.map((job, i) => (
            <div key={i} className="flex items-center justify-between">
              <span className="truncate">{job.label}</span>
              <span className="ml-2 shrink-0">{job.progress.toFixed(0)}%</span>
            </div>
          ))}
        </button>
      )}

      <div className="flex-1" />

      <NavButton active={view === "settings"} label={`⚙ ${t(language, "nav_settings")}`} onClick={() => onNavigate("settings")} />

      <div className="mt-4 border-t border-neutral-200 pt-3 text-xs text-neutral-400 dark:border-neutral-800">
        <div>v{version}</div>
        <div>© {new Date().getFullYear()} Short Maker</div>
      </div>
    </aside>
  );
}
