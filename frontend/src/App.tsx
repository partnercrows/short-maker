import { useEffect, useState } from "react";
import AiClipperView from "./AiClipperView";
import HistoryView from "./HistoryView";
import Sidebar, { type View } from "./Sidebar";
import SettingsView from "./SettingsView";
import YouTubeDownloadView from "./YouTubeDownloadView";
import { loadSettings, saveSettings, type AppSettings } from "./settings";
import type { Project } from "./api";

function App() {
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings());
  const [view, setView] = useState<View>("clipper");
  const [openProject, setOpenProject] = useState<Project | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", settings.theme === "dark");
  }, [settings.theme]);

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
