import { convertFileSrc } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { useState } from "react";
import { copyClipTo, pollJob, type Clip, type Job } from "./api";
import { t, type Language } from "./i18n";
import IntroFramePanel from "./IntroFramePanel";
import SocialKitPanel from "./SocialKitPanel";
import SubtitleStudio from "./SubtitleStudio";
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

function MenuToggleButton({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={`rounded border px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        active
          ? "border-purple-600 bg-purple-600 text-white hover:bg-purple-500"
          : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
      }`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export default function ClipResultCard({ lang, clip, genJob, provider, onGenerate }: Props) {
  const analysis = parseAnalysis(clip);
  const [showPreview, setShowPreview] = useState(false);
  const [showSocialKit, setShowSocialKit] = useState(false);
  const [showSubtitleStudio, setShowSubtitleStudio] = useState(false);
  const [showIntroFrame, setShowIntroFrame] = useState(false);
  const [includeSubtitle, setIncludeSubtitle] = useState(true);
  const [downloadStatus, setDownloadStatus] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloadJob, setDownloadJob] = useState<Job | null>(null);

  const isGenerating = genJob?.status === "queued" || genJob?.status === "running";

  async function handleDownload() {
    setDownloadError(null);
    try {
      const folder = await open({ multiple: false, directory: true });
      if (typeof folder !== "string") return;
      setDownloadStatus("saving");
      const job = await copyClipTo(clip.id, folder);
      setDownloadJob(job);
      const finished = await pollJob(job.id, setDownloadJob);
      if (finished.status === "completed") {
        setDownloadStatus("done");
        setTimeout(() => setDownloadStatus("idle"), 2000);
      } else {
        setDownloadStatus("error");
        setDownloadError(finished.error ?? "");
      }
    } catch (e) {
      setDownloadStatus("error");
      setDownloadError(String(e));
    }
  }

  return (
    <div className="w-full rounded border border-neutral-200 p-4 dark:border-neutral-800">
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

      {/* Primary actions: generating and getting the final file out. */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          className="rounded bg-purple-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
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
          <button
            type="button"
            className="rounded border border-purple-600 px-4 py-1.5 text-sm font-medium text-purple-600 hover:bg-purple-50 disabled:cursor-not-allowed disabled:opacity-50 dark:text-purple-400 dark:hover:bg-purple-950/40"
            onClick={handleDownload}
            disabled={downloadStatus === "saving"}
          >
            {downloadStatus === "saving"
              ? t(lang, "downloading")
              : downloadStatus === "done"
                ? t(lang, "download_done")
                : t(lang, "download")}
          </button>
        )}

        {genJob && (
          <span className="text-xs text-neutral-500">
            {genJob.status}: {genJob.current_step ?? ""} ({genJob.progress.toFixed(0)}%)
          </span>
        )}
        {downloadJob && (downloadJob.status === "queued" || downloadJob.status === "running") && (
          <span className="text-xs text-neutral-500">
            {downloadJob.current_step ?? ""} ({downloadJob.progress.toFixed(0)}%)
          </span>
        )}
      </div>

      {downloadError && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{downloadError}</p>}

      {/* Secondary menu: panels that open below the card. Highlighted while open. */}
      <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-neutral-100 pt-2 dark:border-neutral-900">
        {clip.video_path && (
          <>
            <MenuToggleButton active={showPreview} onClick={() => setShowPreview((s) => !s)}>
              {t(lang, "preview")}
            </MenuToggleButton>
            <MenuToggleButton active={showSubtitleStudio} onClick={() => setShowSubtitleStudio((s) => !s)}>
              {t(lang, "edit_subtitle")}
            </MenuToggleButton>
            <MenuToggleButton active={showIntroFrame} onClick={() => setShowIntroFrame((s) => !s)}>
              {t(lang, "intro_frame")}
            </MenuToggleButton>
          </>
        )}
        <MenuToggleButton active={showSocialKit} onClick={() => setShowSocialKit((s) => !s)}>
          {t(lang, "social_kit")}
        </MenuToggleButton>
      </div>

      {showPreview && clip.video_path && (
        <video controls className="mt-3 max-h-96 w-full rounded bg-black" src={convertFileSrc(clip.video_path)} />
      )}

      {showSocialKit && <SocialKitPanel lang={lang} clipId={clip.id} provider={provider} onClose={() => setShowSocialKit(false)} />}

      {showSubtitleStudio && <SubtitleStudio lang={lang} clipId={clip.id} onClose={() => setShowSubtitleStudio(false)} />}

      {showIntroFrame && (
        <IntroFramePanel lang={lang} clipId={clip.id} videoPath={clip.video_path} onClose={() => setShowIntroFrame(false)} />
      )}
    </div>
  );
}
