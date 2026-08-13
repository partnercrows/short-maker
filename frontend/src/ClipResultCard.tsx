import { convertFileSrc } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { useState } from "react";
import { copyClipTo, type Clip, type Job } from "./api";
import { t, type Language } from "./i18n";
import SocialKitPanel from "./SocialKitPanel";
import type { AppSettings } from "./settings";

function parseAnalysis(clip: Clip) {
  if (!clip.analysis_json) return null;
  try {
    const a = JSON.parse(clip.analysis_json);
    return {
      reason: a.reason as string,
      suggestedTitle: a.suggested_title as string,
      hook: a.hook_score as number,
      curiosity: a.curiosity_score as number,
      emotion: a.emotion_score as number,
      information: a.information_score as number,
    };
  } catch {
    return null;
  }
}

interface Props {
  lang: Language;
  clip: Clip;
  genJob?: Job;
  provider: AppSettings["provider"];
  onGenerate: (clipId: string, includeSubtitle: boolean) => void;
}

export default function ClipResultCard({ lang, clip, genJob, provider, onGenerate }: Props) {
  const analysis = parseAnalysis(clip);
  const [showPreview, setShowPreview] = useState(false);
  const [showSocialKit, setShowSocialKit] = useState(false);
  const [includeSubtitle, setIncludeSubtitle] = useState(true);
  const [downloadStatus, setDownloadStatus] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const isGenerating = genJob?.status === "queued" || genJob?.status === "running";

  async function handleDownload() {
    setDownloadError(null);
    try {
      const folder = await open({ multiple: false, directory: true });
      if (typeof folder !== "string") return;
      setDownloadStatus("saving");
      await copyClipTo(clip.id, folder);
      setDownloadStatus("done");
      setTimeout(() => setDownloadStatus("idle"), 2000);
    } catch (e) {
      setDownloadStatus("error");
      setDownloadError(String(e));
    }
  }

  return (
    <div className="max-w-xl rounded border border-neutral-200 p-4 dark:border-neutral-800">
      <div className="flex justify-between">
        <span className="font-medium">{analysis?.suggestedTitle ?? "(untitled)"}</span>
        <span className="text-purple-600 dark:text-purple-400">{clip.score?.toFixed(0)}/100</span>
      </div>
      <div className="text-xs text-neutral-500">
        {clip.start_time.toFixed(1)}s - {clip.end_time.toFixed(1)}s ({clip.duration.toFixed(1)}s) -- {t(lang, "status_label")}:{" "}
        {clip.status}
      </div>
      {analysis && (
        <>
          <p className="mt-2 text-sm text-neutral-700 dark:text-neutral-300">{analysis.reason}</p>
          <div className="mt-1 text-xs text-neutral-500">
            Hook {analysis.hook} / Curiosity {analysis.curiosity} / Emotion {analysis.emotion} / Info {analysis.information}
          </div>
        </>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          className="rounded bg-neutral-100 px-3 py-1.5 text-sm hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-neutral-800 dark:hover:bg-neutral-700"
          onClick={() => onGenerate(clip.id, includeSubtitle)}
          disabled={isGenerating}
        >
          {t(lang, "generate")}
        </button>
        <label className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-400">
          <input
            type="checkbox"
            checked={includeSubtitle}
            disabled={isGenerating}
            onChange={(e) => setIncludeSubtitle(e.target.checked)}
          />
          {t(lang, "include_subtitle")}
        </label>

        {clip.video_path && (
          <>
            <button
              type="button"
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
              onClick={() => setShowPreview((s) => !s)}
            >
              {showPreview ? t(lang, "close") : t(lang, "preview")}
            </button>
            <button
              type="button"
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
              onClick={handleDownload}
              disabled={downloadStatus === "saving"}
            >
              {downloadStatus === "saving"
                ? t(lang, "downloading")
                : downloadStatus === "done"
                  ? t(lang, "download_done")
                  : t(lang, "download")}
            </button>
          </>
        )}

        <button
          type="button"
          className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
          onClick={() => setShowSocialKit((s) => !s)}
        >
          {showSocialKit ? t(lang, "close") : t(lang, "social_kit")}
        </button>

        {genJob && (
          <span className="text-xs text-neutral-500">
            {genJob.status}: {genJob.current_step ?? ""} ({genJob.progress.toFixed(0)}%)
          </span>
        )}
      </div>

      {downloadError && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{downloadError}</p>}

      {showPreview && clip.video_path && (
        <video controls className="mt-3 max-h-96 w-full rounded bg-black" src={convertFileSrc(clip.video_path)} />
      )}

      {showSocialKit && <SocialKitPanel lang={lang} clipId={clip.id} provider={provider} onClose={() => setShowSocialKit(false)} />}
    </div>
  );
}
