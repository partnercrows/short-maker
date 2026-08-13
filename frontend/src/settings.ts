import type { Language } from "./i18n";

const STORAGE_KEY = "short-maker-settings";

export interface AppSettings {
  theme: "light" | "dark";
  language: Language;
  outputFolder: string;
  useGpu: boolean;
  provider: {
    providerType: string;
    model: string;
    apiKey: string;
    baseUrl: string;
  };
}

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function defaultSettings(): AppSettings {
  return {
    theme: systemPrefersDark() ? "dark" : "light",
    language: "id",
    outputFolder: "",
    useGpu: false,
    provider: { providerType: "gemini", model: "gemini-flash-latest", apiKey: "", baseUrl: "" },
  };
}

export function loadSettings(): AppSettings {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return defaultSettings();
  try {
    return { ...defaultSettings(), ...JSON.parse(raw) };
  } catch {
    return defaultSettings();
  }
}

export function saveSettings(settings: AppSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}
