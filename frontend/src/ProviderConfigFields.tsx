import { useEffect, useState } from "react";
import { listProviderModels, testProviderConnection, type ModelInfo } from "./api";
import { t, type Language } from "./i18n";
import type { AppSettings } from "./settings";

export const PROVIDERS = ["gemini", "openai", "deepseek", "groq", "openrouter", "xai", "mistral", "custom"] as const;

type ProviderValue = AppSettings["provider"];

interface Props {
  lang: Language;
  value: ProviderValue;
  disabled?: boolean;
  onChange: (next: ProviderValue) => void;
}

function Label({ text, required }: { text: string; required?: boolean }) {
  return (
    <label className="mb-1 block text-xs font-medium text-neutral-600 dark:text-neutral-400">
      {text} {required && <span className="text-red-500">*</span>}
    </label>
  );
}

function ApiKeyField({
  lang,
  value,
  disabled,
  onChange,
}: {
  lang: Language;
  value: string;
  disabled?: boolean;
  onChange: (v: string) => void;
}) {
  const [showKey, setShowKey] = useState(false);
  return (
    <div>
      <Label text={t(lang, "api_key")} required />
      <div className="relative">
        <input
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 pr-9 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-800"
          type={showKey ? "text" : "password"}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          tabIndex={-1}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200"
          onClick={() => setShowKey((s) => !s)}
        >
          {showKey ? "🙈" : "👁"}
        </button>
      </div>
    </div>
  );
}

export default function ProviderConfigFields({ lang, value, disabled, onChange }: Props) {
  const isCustom = value.providerType === "custom";

  const [testState, setTestState] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [testDetail, setTestDetail] = useState("");
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);

  // The API key / endpoint this test result applies to changed -- the old
  // "valid" / model list no longer means anything, so drop it.
  useEffect(() => {
    setTestState("idle");
    setTestDetail("");
    setModels(null);
    setModelsError(null);
  }, [value.providerType, value.apiKey, value.baseUrl]);

  function set<K extends keyof ProviderValue>(key: K, v: ProviderValue[K]) {
    onChange({ ...value, [key]: v });
  }

  const canTest = value.apiKey.trim() !== "" && (!isCustom || value.baseUrl.trim() !== "");

  async function handleLoadModels() {
    setLoadingModels(true);
    setModelsError(null);
    try {
      const list = await listProviderModels({
        provider_type: value.providerType,
        api_key: value.apiKey,
        base_url: value.baseUrl || undefined,
      });
      setModels(list);
      if (list.length > 0 && !list.some((m) => m.id === value.model)) {
        set("model", list[0].id);
      }
    } catch (e) {
      setModelsError(String(e));
    } finally {
      setLoadingModels(false);
    }
  }

  async function handleTestConnection() {
    setTestState("testing");
    try {
      const result = await testProviderConnection({
        provider_type: value.providerType,
        api_key: value.apiKey,
        base_url: value.baseUrl || undefined,
      });
      setTestState(result.ok ? "ok" : "error");
      setTestDetail(result.detail);
      if (result.ok && !isCustom) await handleLoadModels();
    } catch (e) {
      setTestState("error");
      setTestDetail(String(e));
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <Label text={t(lang, "provider")} required />
        <select
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-800"
          value={value.providerType}
          disabled={disabled}
          onChange={(e) => onChange({ ...value, providerType: e.target.value })}
        >
          {PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p === "custom" ? "Custom (OpenAI-compatible)" : p}
            </option>
          ))}
        </select>
      </div>

      {isCustom ? (
        <div className="space-y-3 rounded border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-900">
          <h4 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300">
            🔧 {t(lang, "custom_provider_config")}
          </h4>
          <div>
            <Label text={t(lang, "base_url")} required />
            <input
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-800"
              placeholder={t(lang, "base_url_hint_custom")}
              value={value.baseUrl}
              disabled={disabled}
              onChange={(e) => set("baseUrl", e.target.value)}
            />
          </div>
          <div>
            <Label text={t(lang, "model_name")} required />
            <input
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-800"
              value={value.model}
              disabled={disabled}
              onChange={(e) => set("model", e.target.value)}
            />
          </div>
          <ApiKeyField lang={lang} value={value.apiKey} disabled={disabled} onChange={(v) => set("apiKey", v)} />
        </div>
      ) : (
        <ApiKeyField lang={lang} value={value.apiKey} disabled={disabled} onChange={(v) => set("apiKey", v)} />
      )}

      <div>
        <button
          type="button"
          className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
          onClick={handleTestConnection}
          disabled={disabled || !canTest || testState === "testing"}
        >
          {testState === "testing" ? t(lang, "testing_connection") : t(lang, "test_connection")}
        </button>
        {testState === "ok" && <p className="mt-1 text-sm text-green-600 dark:text-green-400">✓ {t(lang, "api_key_valid")}</p>}
        {testState === "error" && (
          <p className="mt-1 text-sm text-red-600 dark:text-red-400">
            ✗ {t(lang, "api_key_invalid")}: {testDetail}
          </p>
        )}
      </div>

      {!isCustom && (
        <div className="rounded border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-900">
          <div className="mb-2 flex items-center justify-between">
            <Label text={t(lang, "ai_model")} required />
            <button
              type="button"
              className="text-xs text-purple-600 hover:underline disabled:opacity-50 dark:text-purple-400"
              onClick={handleLoadModels}
              disabled={disabled || !canTest || loadingModels}
            >
              {loadingModels ? "..." : `↻ ${t(lang, "reload_models")}`}
            </button>
          </div>
          {models && models.length > 0 ? (
            <select
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-800"
              value={value.model}
              disabled={disabled}
              onChange={(e) => set("model", e.target.value)}
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name === m.id ? m.id : `${m.display_name} (${m.id})`}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-800"
              placeholder={t(lang, "model_name_placeholder")}
              value={value.model}
              disabled={disabled}
              onChange={(e) => set("model", e.target.value)}
            />
          )}
          {modelsError && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{modelsError}</p>}
        </div>
      )}
    </div>
  );
}
