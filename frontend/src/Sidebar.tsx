import { useEffect, useState } from "react";
import { getVersion } from "@tauri-apps/api/app";
import { t, type Language } from "./i18n";

export type View = "clipper" | "history" | "settings";

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
      </nav>

      <div className="flex-1" />

      <NavButton active={view === "settings"} label={`⚙ ${t(language, "nav_settings")}`} onClick={() => onNavigate("settings")} />

      <div className="mt-4 border-t border-neutral-200 pt-3 text-xs text-neutral-400 dark:border-neutral-800">
        <div>v{version}</div>
        <div>© {new Date().getFullYear()} Short Maker</div>
      </div>
    </aside>
  );
}
