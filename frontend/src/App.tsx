import { useEffect, useState } from "react";
import AiClipperView from "./AiClipperView";
import HistoryView from "./HistoryView";
import Sidebar, { type View } from "./Sidebar";
import SettingsView from "./SettingsView";
import YouTubeDownloadView from "./YouTubeDownloadView";
import { loadSettings, saveSettings, type AppSettings } from "./settings";
import { waitForBackendReady, type Project } from "./api";
import { t, type Language } from "./i18n";

function StartupGate({ language, onRetry, error }: { language: Language; onRetry: () => void; error: string | null }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <h1 className="text-lg font-semibold">Short Maker</h1>
      {error ? (
        <>
          <p className="max-w-sm text-center text-sm text-red-600 dark:text-red-400">{error}</p>
          <button
            type="button"
            className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500"
            onClick={onRetry}
          >
            {t(language, "app_backend_retry")}
          </button>
        </>
      ) : (
        <>
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-600 border-t-transparent" />
          <p className="text-sm text-neutral-500">{t(language, "app_starting_up")}</p>
        </>
      )}
    </div>
  );
}

function App() {
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings());
  const [view, setView] = useState<View>("clipper");
  const [openProject, setOpenProject] = useState<Project | null>(null);
  const [backendStatus, setBackendStatus] = useState<"loading" | "ready" | "error">("loading");
  const [backendError, setBackendError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", settings.theme === "dark");
  }, [settings.theme]);

  useEffect(() => {
    let cancelled = false;
    setBackendStatus("loading");
    setBackendError(null);
    waitForBackendReady()
      .then(() => {
        if (!cancelled) setBackendStatus("ready");
      })
      .catch((e) => {
        if (!cancelled) {
          setBackendStatus("error");
          setBackendError(String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  function handleSettingsChange(next: AppSettings) {
    setSettings(next);
    saveSettings(next);
  }

  function handleNavigate(next: View) {
    setOpenProject(null);
    setView(next);
  }

  function handleOpenProject(project: Project) {
    setOpenProject(project);
    setView("clipper");
  }

  if (backendStatus !== "ready") {
    return (
      <StartupGate
        language={settings.language}
        error={backendStatus === "error" ? backendError : null}
        onRetry={() => setRetryCount((c) => c + 1)}
      />
    );
  }

  return (
    <div className="flex min-h-screen bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <Sidebar view={view} onNavigate={handleNavigate} language={settings.language} />
      <main className="flex-1 overflow-auto p-6">
        {/* Kept mounted (just hidden) so an in-progress analyze/generate job and its
            polling loop survive switching to another menu, instead of being destroyed. */}
        <div className={view === "clipper" ? "" : "hidden"}>
          <AiClipperView settings={settings} onSettingsChange={handleSettingsChange} openProject={openProject} />
        </div>
        {view === "history" && <HistoryView language={settings.language} onOpenProject={handleOpenProject} />}
        {view === "youtube_download" && <YouTubeDownloadView language={settings.language} />}
        {view === "settings" && <SettingsView settings={settings} onChange={handleSettingsChange} />}
      </main>
    </div>
  );
}

export default App;
