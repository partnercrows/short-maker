import { useEffect, useState } from "react";
import { getVersion } from "@tauri-apps/api/app";
import { open } from "@tauri-apps/plugin-dialog";
import { getCapabilities, type SystemCapabilities } from "./api";
import { t } from "./i18n";
import type { AppSettings } from "./settings";
import { checkForUpdate, type UpdateCheckResult } from "./updater";

const PROVIDERS = ["gemini", "openai", "deepseek", "groq", "openrouter", "xai", "mistral", "custom"] as const;

interface Props {
  settings: AppSettings;
  onChange: (settings: AppSettings) => void;
}

export default function SettingsView({ settings, onChange }: Props) {
  const lang = settings.language;
  const [draft, setDraft] = useState<AppSettings>(settings);
  const [saved, setSaved] = useState(false);
  const [version, setVersion] = useState("0.1.0");
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [updateResult, setUpdateResult] = useState<UpdateCheckResult | null>(null);
  const [installingUpdate, setInstallingUpdate] = useState(false);

  async function handleCheckUpdate() {
    setCheckingUpdate(true);
    setUpdateResult(null);
    const result = await checkForUpdate();
    setUpdateResult(result);
    setCheckingUpdate(false);
  }

  async function handleInstallUpdate() {
    if (updateResult?.status !== "available") return;
    setInstallingUpdate(true);
    try {
      await updateResult.install();
    } catch (e) {
      setUpdateResult({ status: "error", message: String(e) });
    } finally {
      setInstallingUpdate(false);
    }
  }
  const [capabilities, setCapabilities] = useState<SystemCapabilities | null>(null);
  const [capabilitiesStatus, setCapabilitiesStatus] = useState<"loading" | "ready" | "error">("loading");
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(null);

  function checkCapabilities() {
    setCapabilitiesStatus("loading");
    setCapabilitiesError(null);
    getCapabilities()
      .then((caps) => {
        setCapabilities(caps);
        setCapabilitiesStatus("ready");
      })
      .catch((e) => {
        setCapabilitiesStatus("error");
        setCapabilitiesError(String(e));
      });
  }

  useEffect(() => {
    getVersion()
      .then(setVersion)
      .catch(() => {});
    checkCapabilities();
  }, []);

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  function updateProvider<K extends keyof AppSettings["provider"]>(key: K, value: AppSettings["provider"][K]) {
    setDraft((prev) => ({ ...prev, provider: { ...prev.provider, [key]: value } }));
    setSaved(false);
  }

  async function handleBrowseFolder() {
    const path = await open({ multiple: false, directory: true });
    if (typeof path === "string") update("outputFolder", path);
  }

  function handleSave() {
    onChange(draft);
    setSaved(true);
  }

  return (
    <div className="max-w-lg space-y-8">
      <h2 className="text-lg font-semibold">{t(lang, "nav_settings")}</h2>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-neutral-500">{t(lang, "settings_appearance")}</h3>
        <div>
          <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">
            {t(lang, "settings_theme")}
          </label>
          <div className="flex gap-2">
            <button
              className={`rounded px-3 py-1.5 text-sm ${draft.theme === "light" ? "bg-purple-600 text-white" : "border border-neutral-300 dark:border-neutral-700"}`}
              onClick={() => update("theme", "light")}
            >
              ☀️ {t(lang, "settings_theme_light")}
            </button>
            <button
              className={`rounded px-3 py-1.5 text-sm ${draft.theme === "dark" ? "bg-purple-600 text-white" : "border border-neutral-300 dark:border-neutral-700"}`}
              onClick={() => update("theme", "dark")}
            >
              🌙 {t(lang, "settings_theme_dark")}
            </button>
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">
            {t(lang, "settings_language")}
          </label>
          <div className="flex gap-2">
            <button
              className={`rounded px-3 py-1.5 text-sm ${draft.language === "id" ? "bg-purple-600 text-white" : "border border-neutral-300 dark:border-neutral-700"}`}
              onClick={() => update("language", "id")}
            >
              Bahasa Indonesia
            </button>
            <button
              className={`rounded px-3 py-1.5 text-sm ${draft.language === "en" ? "bg-purple-600 text-white" : "border border-neutral-300 dark:border-neutral-700"}`}
              onClick={() => update("language", "en")}
            >
              English
            </button>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-neutral-500">{t(lang, "settings_ai_provider")}</h3>
        <p className="text-xs text-neutral-500">{t(lang, "settings_ai_provider_hint")}</p>
        <div>
          <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">{t(lang, "provider")}</label>
          <select
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
            value={draft.provider.providerType}
            onChange={(e) => updateProvider("providerType", e.target.value)}
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>
                {p === "custom" ? "Custom (OpenAI-compatible)" : p}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">{t(lang, "model")}</label>
          <input
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
            value={draft.provider.model}
            onChange={(e) => updateProvider("model", e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">{t(lang, "api_key")}</label>
          <input
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
            type="password"
            value={draft.provider.apiKey}
            onChange={(e) => updateProvider("apiKey", e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">{t(lang, "base_url")}</label>
          <input
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
            placeholder={draft.provider.providerType === "custom" ? t(lang, "base_url_hint_custom") : t(lang, "base_url_hint_default")}
            value={draft.provider.baseUrl}
            onChange={(e) => updateProvider("baseUrl", e.target.value)}
          />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-neutral-500">{t(lang, "settings_output")}</h3>
        <p className="text-xs text-neutral-500">{t(lang, "settings_output_hint")}</p>
        <div className="flex gap-2">
          <input
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
            placeholder={t(lang, "settings_output_placeholder")}
            value={draft.outputFolder}
            onChange={(e) => update("outputFolder", e.target.value)}
          />
          <button
            className="whitespace-nowrap rounded border border-neutral-300 px-3 py-2 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
            onClick={handleBrowseFolder}
          >
            {t(lang, "browse")}
          </button>
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-neutral-500">{t(lang, "settings_performance")}</h3>
          <button
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
            onClick={checkCapabilities}
            disabled={capabilitiesStatus === "loading"}
          >
            {capabilitiesStatus === "loading" ? "..." : `↻ ${t(lang, "settings_gpu_recheck")}`}
          </button>
        </div>

        {capabilitiesStatus === "loading" && <p className="text-sm text-neutral-500">{t(lang, "settings_gpu_checking")}</p>}

        {capabilitiesStatus === "error" && (
          <p className="text-sm text-red-600 dark:text-red-400">
            {t(lang, "settings_gpu_check_failed")}: {capabilitiesError}
          </p>
        )}

        {capabilitiesStatus === "ready" && capabilities && (
          <>
            <div className="text-sm text-neutral-600 dark:text-neutral-400">
              {capabilities.gpu_name ?? "CPU only"} {capabilities.gpu_name && `(${capabilities.detail})`}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.useGpu}
                disabled={!capabilities.gpu_transcription_ready}
                onChange={(e) => update("useGpu", e.target.checked)}
              />
              {t(lang, "settings_gpu_use")}
            </label>
            {!capabilities.gpu_transcription_ready && (
              <p className="text-xs text-amber-600 dark:text-amber-400">{t(lang, "settings_gpu_not_available")}</p>
            )}
            {capabilities.gpu_transcription_ready && <p className="text-xs text-neutral-500">{t(lang, "settings_gpu_speedup")}</p>}
          </>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-neutral-500">{t(lang, "settings_update")}</h3>
        <div className="text-sm text-neutral-600 dark:text-neutral-400">
          {t(lang, "settings_update_current_version")}: v{version}
        </div>
        <button
          className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
          onClick={handleCheckUpdate}
          disabled={checkingUpdate}
        >
          {checkingUpdate ? "..." : t(lang, "settings_update_check")}
        </button>

        {updateResult?.status === "up-to-date" && (
          <p className="text-sm text-green-600 dark:text-green-400">{t(lang, "settings_update_up_to_date")}</p>
        )}
        {updateResult?.status === "error" && (
          <p className="text-sm text-red-600 dark:text-red-400">
            {t(lang, "settings_update_check_failed")}: {updateResult.message}
          </p>
        )}
        {updateResult?.status === "available" && (
          <div className="rounded border border-purple-300 p-3 dark:border-purple-800">
            <p className="text-sm">
              {t(lang, "settings_update_available")}: v{updateResult.version}
            </p>
            {updateResult.body && <p className="mt-1 text-xs text-neutral-500">{updateResult.body}</p>}
            <button
              className="mt-2 rounded bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
              onClick={handleInstallUpdate}
              disabled={installingUpdate}
            >
              {installingUpdate ? t(lang, "settings_update_installing") : t(lang, "settings_update_install")}
            </button>
          </div>
        )}
      </section>

      <div className="flex items-center gap-3 border-t border-neutral-200 pt-4 dark:border-neutral-800">
        <button className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500" onClick={handleSave}>
          {t(lang, "settings_save")}
        </button>
        {saved && <span className="text-sm text-green-600 dark:text-green-400">{t(lang, "settings_saved")}</span>}
      </div>
    </div>
  );
}
