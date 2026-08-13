import { useEffect, useState } from "react";
import { generateSocialKit, getSocialKits, regenerateSocialKit, type SocialKit, type TitleOption } from "./api";
import { t, type Language } from "./i18n";
import type { AppSettings } from "./settings";

const PLATFORMS = ["youtube_shorts", "tiktok", "instagram_reels", "facebook_reels"] as const;

const PLATFORM_LABEL: Record<string, string> = {
  youtube_shorts: "YouTube Shorts",
  tiktok: "TikTok",
  instagram_reels: "Instagram Reels",
  facebook_reels: "Facebook Reels",
};

function parseTitles(titlesJson: string | null): TitleOption[] {
  if (!titlesJson) return [];
  try {
    return JSON.parse(titlesJson);
  } catch {
    return [];
  }
}

function CopyButton({ text, lang }: { text: string; lang: Language }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard access can be denied by the platform -- fail silently, the
      // text is already visible on screen for the user to select manually.
    }
  }

  return (
    <button
      type="button"
      className="shrink-0 rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
      onClick={handleCopy}
    >
      {copied ? t(lang, "copied") : t(lang, "copy")}
    </button>
  );
}

interface Props {
  lang: Language;
  clipId: string;
  provider: AppSettings["provider"];
  onClose: () => void;
}

export default function SocialKitPanel({ lang, clipId, provider, onClose }: Props) {
  const [platform, setPlatform] = useState<(typeof PLATFORMS)[number]>("youtube_shorts");
  const [kits, setKits] = useState<SocialKit[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getSocialKits(clipId)
      .then(setKits)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [clipId]);

  const kit = kits.find((k) => k.platform === platform) ?? null;

  async function handleGenerate() {
    setError(null);
    setGenerating(true);
    try {
      const providerConfig = {
        provider_type: provider.providerType,
        model: provider.model,
        api_key: provider.apiKey,
        base_url: provider.baseUrl || undefined,
      };
      const result = kit
        ? await regenerateSocialKit(clipId, platform, providerConfig)
        : await generateSocialKit(clipId, platform, providerConfig);
      setKits((prev) => [result, ...prev.filter((k) => k.platform !== platform)]);
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  }

  const titles = parseTitles(kit?.titles_json ?? null);
  const hashtagList = kit?.hashtags ? kit.hashtags.split(/\s+/).filter(Boolean) : [];

  return (
    <div className="mt-3 rounded border border-purple-200 bg-purple-50/50 p-4 dark:border-purple-900 dark:bg-purple-950/30">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold">{t(lang, "social_kit")}</h4>
        <button type="button" className="text-xs text-neutral-500 hover:underline" onClick={onClose}>
          {t(lang, "close")}
        </button>
      </div>

      <div className="mb-3">
        <select
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-800"
          value={platform}
          disabled={generating}
          onChange={(e) => setPlatform(e.target.value as (typeof PLATFORMS)[number])}
        >
          {PLATFORMS.map((p) => (
            <option key={p} value={p}>
              {PLATFORM_LABEL[p]}
            </option>
          ))}
        </select>
      </div>

      {error && <div className="mb-3 rounded bg-red-100 p-2 text-xs text-red-700 dark:bg-red-900 dark:text-red-100">{error}</div>}

      {loading ? (
        <p className="text-sm text-neutral-500">{t(lang, "loading")}</p>
      ) : (
        <>
          {kit && (
            <div className="mb-3 space-y-3 text-sm">
              <div>
                <div className="mb-1 font-medium">{t(lang, "social_kit_titles")}</div>
                {titles.map((opt, i) => (
                  <div key={i} className="mb-1 flex items-center justify-between gap-2 rounded bg-white p-2 dark:bg-neutral-900">
                    <div>
                      <span className="mr-2 text-purple-600 dark:text-purple-400">{opt.score.toFixed(0)}</span>
                      {opt.title}
                    </div>
                    <CopyButton text={opt.title} lang={lang} />
                  </div>
                ))}
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-medium">{t(lang, "social_kit_description")}</span>
                  {kit.description && <CopyButton text={kit.description} lang={lang} />}
                </div>
                <p className="whitespace-pre-wrap rounded bg-white p-2 text-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
                  {kit.description}
                </p>
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-medium">{t(lang, "social_kit_hashtags")}</span>
                  {kit.hashtags && <CopyButton text={kit.hashtags} lang={lang} />}
                </div>
                <div className="flex flex-wrap gap-1">
                  {hashtagList.map((tag) => (
                    <span key={tag} className="rounded bg-white px-2 py-0.5 text-xs text-purple-600 dark:bg-neutral-900 dark:text-purple-400">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-medium">{t(lang, "social_kit_thumbnail_idea")}</span>
                  {kit.thumbnail_idea && <CopyButton text={kit.thumbnail_idea} lang={lang} />}
                </div>
                <p className="whitespace-pre-wrap rounded bg-white p-2 text-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
                  {kit.thumbnail_idea}
                </p>
              </div>

              {kit.thumbnail_prompt && (
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-medium">{t(lang, "social_kit_thumbnail_prompt")}</span>
                    <CopyButton text={kit.thumbnail_prompt} lang={lang} />
                  </div>
                  <p className="whitespace-pre-wrap rounded bg-white p-2 text-xs text-neutral-500 dark:bg-neutral-900">
                    {kit.thumbnail_prompt}
                  </p>
                </div>
              )}
            </div>
          )}

          <button
            type="button"
            className="rounded bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={handleGenerate}
            disabled={generating}
          >
            {generating ? t(lang, "generating_social_kit") : kit ? t(lang, "regenerate") : t(lang, "generate_social_kit")}
          </button>
        </>
      )}
    </div>
  );
}
