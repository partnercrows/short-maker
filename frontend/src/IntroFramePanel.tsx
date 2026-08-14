import { convertFileSrc } from "@tauri-apps/api/core";
import { useEffect, useRef, useState } from "react";
import { captureIntroFrame, getIntroFrame, updateIntroFrame, uploadIntroFrame, type IntroFrameResponse } from "./api";
import { t, type Language } from "./i18n";

interface Props {
  lang: Language;
  clipId: string;
  videoPath: string | null;
  onClose: () => void;
}

export default function IntroFramePanel({ lang, clipId, videoPath, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<IntroFrameResponse | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [duration, setDuration] = useState(2);
  const [captureTimestamp, setCaptureTimestamp] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [capturing, setCapturing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [previewing, setPreviewing] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function load() {
    setLoading(true);
    setError(null);
    getIntroFrame(clipId)
      .then((res) => {
        setData(res);
        setEnabled(res.intro.enabled);
        setDuration(res.intro.duration_seconds);
        setCaptureTimestamp(res.intro.source_timestamp ?? 0);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(load, [clipId]);

  async function handleToggleEnabled(next: boolean) {
    setEnabled(next);
    setError(null);
    try {
      setData(await updateIntroFrame(clipId, next, duration));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDurationCommit(next: number) {
    setDuration(next);
    setError(null);
    try {
      setData(await updateIntroFrame(clipId, enabled, next));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleCapture() {
    setCapturing(true);
    setError(null);
    try {
      const res = await captureIntroFrame(clipId, captureTimestamp, duration);
      setData(res);
      setEnabled(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setCapturing(false);
    }
  }

  async function handleFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const res = await uploadIntroFrame(clipId, file, duration);
      setData(res);
      setEnabled(true);
    } catch (err) {
      setError(String(err));
    } finally {
      setUploading(false);
    }
  }

  function handlePreview() {
    if (!data?.image_path) return;
    setPreviewing(true);
    videoRef.current?.pause();
    setTimeout(() => {
      setPreviewing(false);
      videoRef.current?.play();
    }, duration * 1000);
  }

  return (
    <div className="mt-3 rounded border border-purple-200 bg-purple-50/50 p-4 dark:border-purple-900 dark:bg-purple-950/30">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold">{t(lang, "intro_panel_title")}</h4>
        <button type="button" className="text-xs text-neutral-500 hover:underline" onClick={onClose}>
          {t(lang, "close")}
        </button>
      </div>

      {loading && <p className="text-sm text-neutral-500">{t(lang, "loading")}</p>}
      {error && <div className="mb-3 rounded bg-red-100 p-2 text-xs text-red-700 dark:bg-red-900 dark:text-red-100">{error}</div>}

      {!loading && (
        <>
          <label className="mb-3 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(e) => handleToggleEnabled(e.target.checked)} />
            {t(lang, "intro_enable")}
          </label>

          <div className="mb-3 flex items-center gap-2 text-sm">
            <span className="text-neutral-500">{t(lang, "intro_duration")}</span>
            <input
              type="number"
              step={0.1}
              min={0.1}
              className="w-20 rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-800"
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              onBlur={(e) => handleDurationCommit(Number(e.target.value))}
            />
          </div>

          <div className="mb-3 grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-xs font-medium text-neutral-500">{t(lang, "intro_source_captured")}</p>
              {videoPath && (
                <video
                  ref={videoRef}
                  src={convertFileSrc(videoPath)}
                  className="mb-1 max-h-48 w-fit rounded bg-black"
                  onLoadedMetadata={(e) => setVideoDuration(e.currentTarget.duration)}
                  muted
                />
              )}
              <input
                type="range"
                className="w-full"
                min={0}
                max={videoDuration || 0}
                step={0.1}
                value={Math.min(captureTimestamp, videoDuration || 0)}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  setCaptureTimestamp(value);
                  if (videoRef.current) videoRef.current.currentTime = value;
                }}
              />
              <button
                type="button"
                className="mt-1 rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
                onClick={handleCapture}
                disabled={capturing || !videoPath}
              >
                {capturing ? t(lang, "intro_capturing") : t(lang, "intro_use_this_frame")}
              </button>
            </div>

            <div>
              <p className="mb-1 text-xs font-medium text-neutral-500">{t(lang, "intro_source_uploaded")}</p>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={handleFileChosen}
              />
              <button
                type="button"
                className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                {uploading ? t(lang, "intro_uploading") : t(lang, "intro_upload_button")}
              </button>
              <p className="mt-2 text-xs text-neutral-400">{t(lang, "intro_source_social_kit")}</p>
            </div>
          </div>

          <div className="mb-2">
            <p className="mb-1 text-xs font-medium text-neutral-500">{t(lang, "intro_current_image")}</p>
            {data?.image_path ? (
              <img
                // Capture and upload both write to the same fixed `intro.png` path, so the
                // URL alone doesn't change when the image is replaced -- append the intro
                // document's timestamp to force the webview to refetch instead of reusing
                // a cached image for that URL.
                src={`${convertFileSrc(data.image_path)}?t=${encodeURIComponent(data.intro.created_at)}`}
                alt=""
                className="max-h-32 rounded border border-neutral-300 dark:border-neutral-700"
              />
            ) : (
              <p className="text-xs text-neutral-500">{t(lang, "intro_no_image_yet")}</p>
            )}
          </div>

          {data?.image_path && videoPath && (
            <button
              type="button"
              className="rounded bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
              onClick={handlePreview}
              disabled={previewing}
            >
              {t(lang, "intro_preview")}
            </button>
          )}
          {previewing && data?.image_path && (
            <div className="relative mt-2 inline-block">
              <img
                src={`${convertFileSrc(data.image_path)}?t=${encodeURIComponent(data.intro.created_at)}`}
                alt=""
                className="max-h-48 rounded bg-black"
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
