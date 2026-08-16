import { open } from "@tauri-apps/plugin-dialog";
import { useState } from "react";
import {
  downloadYoutubeMedia,
  getYoutubeVideoInfo,
  pollJob,
  type Job,
  type YoutubeDownloadFormat,
  type YoutubeVideoInfo,
} from "./api";
import { t, type Language } from "./i18n";

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function ProgressBar({ progress }: { progress: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded bg-neutral-200 dark:bg-neutral-800">
      <div className="h-full bg-purple-600 transition-all" style={{ width: `${progress}%` }} />
    </div>
  );
}

interface Props {
  language: Language;
}

export default function YouTubeDownloadView({ language: lang }: Props) {
  const [url, setUrl] = useState("");
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [info, setInfo] = useState<YoutubeVideoInfo | null>(null);
  const [format, setFormat] = useState<YoutubeDownloadFormat>("video");
  const [resolution, setResolution] = useState<number | null>(null);
  const [outputFolder, setOutputFolder] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function handleCheck() {
    if (!url.trim()) return;
    setChecking(true);
    setCheckError(null);
    setInfo(null);
    setJob(null);
    setDownloadError(null);
    try {
      const result = await getYoutubeVideoInfo(url.trim());
      setInfo(result);
      setResolution(result.available_resolutions[0] ?? null);
    } catch (e) {
      setCheckError(String(e));
    } finally {
      setChecking(false);
    }
  }

  async function handleChooseFolder() {
    const folder = await open({ multiple: false, directory: true });
    if (typeof folder === "string") setOutputFolder(folder);
  }

  async function handleDownload() {
    if (!info || !outputFolder || (format === "video" && resolution == null)) return;
    setDownloading(true);
    setDownloadError(null);
    setJob(null);
    try {
      const created = await downloadYoutubeMedia(url.trim(), format, format === "video" ? resolution : null, outputFolder);
      setJob(created);
      const finished = await pollJob(created.id, setJob);
      if (finished.status === "failed") {
        setDownloadError(finished.error ?? "");
      }
    } catch (e) {
      setDownloadError(String(e));
    } finally {
      setDownloading(false);
    }
  }

  const jobRunning = job?.status === "queued" || job?.status === "running";
  const jobDone = job?.status === "completed";
  const canDownload = !downloading && !jobRunning && !!outputFolder && (format === "audio" || resolution != null);

  return (
    <div className="max-w-xl space-y-4">
      <h2 className="text-lg font-semibold">{t(lang, "youtube_download_title")}</h2>

      <div>
        <label className="mb-1 block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t(lang, "youtube_url_label")}
        </label>
        <div className="flex gap-2">
          <input
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
            placeholder={t(lang, "youtube_url_placeholder")}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={checking}
          />
          <button
            type="button"
            className="shrink-0 rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={handleCheck}
            disabled={checking || !url.trim()}
          >
            {checking ? t(lang, "youtube_checking") : t(lang, "youtube_check_video")}
          </button>
        </div>
        {checkError && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{checkError}</p>}
      </div>

      {info && (
        <div className="rounded border border-neutral-200 p-3 dark:border-neutral-800">
          <div className="flex gap-3">
            {info.thumbnail_url && <img src={info.thumbnail_url} alt="" className="h-20 w-36 shrink-0 rounded object-cover" />}
            <div>
              <div className="font-medium">{info.title}</div>
              {info.duration != null && (
                <div className="text-xs text-neutral-500">
                  {t(lang, "youtube_duration_label")}: {formatDuration(info.duration)}
                </div>
              )}
            </div>
          </div>

          <div className="mt-3">
            <div className="mb-1 text-xs font-medium text-neutral-500">{t(lang, "youtube_format_label")}</div>
            <div className="flex gap-2">
              <button
                type="button"
                className={`rounded border px-3 py-1 text-sm ${
                  format === "video"
                    ? "border-purple-600 bg-purple-600 text-white"
                    : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                }`}
                onClick={() => setFormat("video")}
              >
                {t(lang, "youtube_format_video")}
              </button>
              <button
                type="button"
                className={`rounded border px-3 py-1 text-sm ${
                  format === "audio"
                    ? "border-purple-600 bg-purple-600 text-white"
                    : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                }`}
                onClick={() => setFormat("audio")}
              >
                {t(lang, "youtube_format_audio")}
              </button>
            </div>
          </div>

          {format === "video" && (
            <div className="mt-3">
              <div className="mb-1 text-xs font-medium text-neutral-500">{t(lang, "youtube_resolution_label")}</div>
              {info.available_resolutions.length === 0 ? (
                <p className="text-sm text-neutral-500">{t(lang, "youtube_no_resolutions")}</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {info.available_resolutions.map((r) => (
                    <button
                      key={r}
                      type="button"
                      className={`rounded border px-3 py-1 text-sm ${
                        resolution === r
                          ? "border-purple-600 bg-purple-600 text-white"
                          : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                      }`}
                      onClick={() => setResolution(r)}
                    >
                      {r}p
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="mt-3">
            <div className="mb-1 text-xs font-medium text-neutral-500">{t(lang, "youtube_destination_label")}</div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                onClick={handleChooseFolder}
              >
                {t(lang, "youtube_choose_folder")}
              </button>
              <span className="truncate text-xs text-neutral-500">{outputFolder ?? t(lang, "youtube_no_folder_chosen")}</span>
            </div>
          </div>

          <button
            type="button"
            className="mt-3 rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={handleDownload}
            disabled={!canDownload}
          >
            {downloading || jobRunning ? t(lang, "youtube_downloading") : t(lang, "youtube_download_button")}
          </button>

          {(jobRunning || jobDone) && (
            <div className="mt-3">
              <ProgressBar progress={job?.progress ?? 0} />
              <div className="mt-1 flex items-center justify-between text-xs text-neutral-500">
                <span>{job?.current_step ?? ""}</span>
                <span>{(job?.progress ?? 0).toFixed(0)}%</span>
              </div>
            </div>
          )}
          {jobDone && <p className="mt-1 text-xs text-green-600 dark:text-green-400">{t(lang, "youtube_download_done")}</p>}
          {downloadError && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{downloadError}</p>}
        </div>
      )}
    </div>
  );
}
