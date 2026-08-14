import { convertFileSrc } from "@tauri-apps/api/core";
import { useEffect, useRef, useState } from "react";
import {
  applySubtitleStyle,
  getSubtitleDocument,
  pollJob,
  renderSubtitleJob,
  saveSubtitleDocument,
  type Job,
  type SubtitleDocument,
  type SubtitleDocumentLine,
  type SubtitleStyle,
} from "./api";
import { t, type Language } from "./i18n";
import SubtitleStyleEditor, { type StyleScope } from "./SubtitleStyleEditor";
import { CANVAS_HEIGHT, CANVAS_WIDTH } from "./subtitlePresets";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

function hexToRgba(hex: string, opacity: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16) || 0;
  const g = parseInt(h.slice(2, 4), 16) || 0;
  const b = parseInt(h.slice(4, 6), 16) || 0;
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

function buildOverlayStyle(style: SubtitleStyle, scale: number): React.CSSProperties {
  const leftPct = (style.position.x / CANVAS_WIDTH) * 100;
  const topPct = (style.position.y / CANVAS_HEIGHT) * 100;
  const translateX = style.alignment === "left" ? "0%" : style.alignment === "right" ? "-100%" : "-50%";
  const fontSizePx = style.font_size * scale;

  const textShadows: string[] = [];
  if (style.shadow.enabled) {
    textShadows.push(
      `${style.shadow.offset_x * scale}px ${style.shadow.offset_y * scale}px ${style.shadow.blur * scale}px ${hexToRgba(style.shadow.color, style.shadow.opacity)}`,
    );
  }
  if (style.glow.enabled) {
    const glowColor = hexToRgba(style.glow.color, style.glow.opacity);
    textShadows.push(`0 0 ${style.glow.blur * scale}px ${glowColor}`);
    textShadows.push(`0 0 ${style.glow.blur * scale * 2}px ${glowColor}`);
  }

  return {
    position: "absolute",
    left: `${leftPct}%`,
    top: `${topPct}%`,
    transform: `translate(${translateX}, -50%)`,
    fontFamily: style.font_family,
    fontSize: `${fontSizePx}px`,
    fontWeight: style.font_weight,
    color: style.text_color,
    textAlign: style.alignment,
    whiteSpace: "pre-wrap",
    maxWidth: "90%",
    WebkitTextStroke: style.stroke.enabled ? `${style.stroke.width * scale}px ${style.stroke.color}` : undefined,
    textShadow: textShadows.length ? textShadows.join(", ") : undefined,
    pointerEvents: "none",
    ...(style.background.enabled
      ? {
          backgroundColor: hexToRgba(style.background.color, style.background.opacity),
          borderRadius: `${style.background.border_radius * scale}px`,
          padding: `${style.background.padding * scale}px`,
        }
      : {}),
  };
}

function splitLine(line: SubtitleDocumentLine): [SubtitleDocumentLine, SubtitleDocumentLine] {
  const words = line.words ?? line.text.split(" ").map((w) => ({ text: w, start: 0, end: 0, style: null }));
  const mid = Math.max(1, Math.ceil(words.length / 2));
  const firstWords = words.slice(0, mid);
  const secondWords = words.slice(mid);
  const ratio = secondWords.length === 0 ? 0.5 : mid / words.length;
  const splitTime = line.start + (line.end - line.start) * ratio;

  return [
    {
      id: crypto.randomUUID(),
      start: line.start,
      end: splitTime,
      text: firstWords.map((w) => w.text).join(" "),
      words: line.words ? firstWords : null,
      style: line.style,
    },
    {
      id: crypto.randomUUID(),
      start: splitTime,
      end: line.end,
      text: secondWords.map((w) => w.text).join(" ") || "...",
      words: line.words ? secondWords : null,
      style: line.style,
    },
  ];
}

function mergeLines(a: SubtitleDocumentLine, b: SubtitleDocumentLine): SubtitleDocumentLine {
  return {
    id: a.id,
    start: a.start,
    end: b.end,
    text: `${a.text} ${b.text}`.trim(),
    words: a.words && b.words ? [...a.words, ...b.words] : null,
    style: a.style,
  };
}

function applyStyleToDocumentLocally(
  document: SubtitleDocument,
  scope: StyleScope,
  lineIds: string[],
  style: SubtitleStyle,
): SubtitleDocument {
  if (scope === "clip") {
    return { ...document, default_style: style };
  }
  const idSet = new Set(lineIds);
  return {
    ...document,
    lines: document.lines.map((l) => (idSet.has(l.id) ? { ...l, style } : l)),
  };
}

interface Props {
  lang: Language;
  clipId: string;
  onClose: () => void;
}

export default function SubtitleStudio({ lang, clipId, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [document, setDocument] = useState<SubtitleDocument | null>(null);
  const [needsRebuild, setNeedsRebuild] = useState(false);
  const [renderedVideoPath, setRenderedVideoPath] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [renderJob, setRenderJob] = useState<Job | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [scale, setScale] = useState(0);
  const [selectedLineIds, setSelectedLineIds] = useState<Set<string>>(new Set());
  const [showStyleEditor, setShowStyleEditor] = useState(false);
  const [styleScope, setStyleScope] = useState<StyleScope>("clip");
  const [draftStyle, setDraftStyle] = useState<SubtitleStyle | null>(null);
  const [applying, setApplying] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  function loadDocument() {
    setLoading(true);
    setError(null);
    getSubtitleDocument(clipId)
      .then((res) => {
        setDocument(res.document);
        setNeedsRebuild(res.needs_rebuild);
        setRenderedVideoPath(res.rendered_video_path);
        setDirty(false);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(loadDocument, [clipId]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const height = entries[0]?.contentRect.height ?? 0;
      setScale(height / CANVAS_HEIGHT);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [renderedVideoPath]);

  function updateLines(next: SubtitleDocumentLine[]) {
    if (!document) return;
    setDocument({ ...document, lines: next });
    setDirty(true);
    setSaved(false);
  }

  function handleTextChange(id: string, text: string) {
    if (!document) return;
    updateLines(document.lines.map((l) => (l.id === id ? { ...l, text } : l)));
  }

  function handleTimingChange(id: string, field: "start" | "end", value: number) {
    if (!document) return;
    updateLines(document.lines.map((l) => (l.id === id ? { ...l, [field]: value } : l)));
  }

  function handleSplit(id: string) {
    if (!document) return;
    const index = document.lines.findIndex((l) => l.id === id);
    if (index === -1) return;
    const [first, second] = splitLine(document.lines[index]);
    const next = [...document.lines];
    next.splice(index, 1, first, second);
    updateLines(next);
  }

  function handleMergeWithNext(id: string) {
    if (!document) return;
    const index = document.lines.findIndex((l) => l.id === id);
    if (index === -1 || index === document.lines.length - 1) return;
    const merged = mergeLines(document.lines[index], document.lines[index + 1]);
    const next = [...document.lines];
    next.splice(index, 2, merged);
    updateLines(next);
  }

  function handleDelete(id: string) {
    if (!document) return;
    updateLines(document.lines.filter((l) => l.id !== id));
  }

  function handleAddLine() {
    if (!document) return;
    const last = document.lines[document.lines.length - 1];
    const start = last ? last.end : currentTime;
    const newLine: SubtitleDocumentLine = {
      id: crypto.randomUUID(),
      start,
      end: start + 2,
      text: t(lang, "subtitle_new_line_placeholder"),
      words: null,
      style: null,
    };
    updateLines([...document.lines, newLine]);
  }

  function handleJumpTo(line: SubtitleDocumentLine) {
    if (videoRef.current) videoRef.current.currentTime = line.start;
  }

  function toggleLineSelected(id: string) {
    setSelectedLineIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function openStyleEditor() {
    if (!document) return;
    const base = document.lines.find((l) => currentTime >= l.start && currentTime < l.end) ?? null;
    setStyleScope(base ? "line" : "clip");
    setDraftStyle(base?.style ?? document.default_style);
    setShowStyleEditor(true);
  }

  function closeStyleEditor() {
    setShowStyleEditor(false);
    setDraftStyle(null);
  }

  async function handleApplyStyle() {
    if (!document || !draftStyle) return;
    const baseActiveLine = document.lines.find((l) => currentTime >= l.start && currentTime < l.end) ?? null;
    const lineIds =
      styleScope === "line" ? (baseActiveLine ? [baseActiveLine.id] : []) : styleScope === "lines" ? Array.from(selectedLineIds) : undefined;
    if ((styleScope === "line" || styleScope === "lines") && (!lineIds || lineIds.length === 0)) return;
    setApplying(true);
    setError(null);
    try {
      const updated = await applySubtitleStyle(clipId, { scope: styleScope, line_ids: lineIds, style: draftStyle });
      setDocument(updated);
      setDirty(false);
      closeStyleEditor();
    } catch (e) {
      setError(String(e));
    } finally {
      setApplying(false);
    }
  }

  async function handleSave() {
    if (!document) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await saveSubtitleDocument(clipId, document);
      setDocument(saved);
      setDirty(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleRender() {
    if (!document) return;
    setRenderError(null);
    try {
      if (dirty) await handleSave();
      const job = await renderSubtitleJob(clipId);
      setRenderJob(job);
      const finished = await pollJob(job.id, setRenderJob);
      if (finished.status === "completed") {
        loadDocument(); // rendered.mp4 may now exist for the first time (legacy-clip rebuild)
      } else if (finished.status === "failed") {
        setRenderError(finished.error ?? "");
      }
    } catch (e) {
      setRenderError(String(e));
    }
  }

  const baseActiveLine = document?.lines.find((l) => currentTime >= l.start && currentTime < l.end) ?? null;
  const previewDocument =
    showStyleEditor && draftStyle && document
      ? applyStyleToDocumentLocally(
          document,
          styleScope,
          styleScope === "line" ? (baseActiveLine ? [baseActiveLine.id] : []) : Array.from(selectedLineIds),
          draftStyle,
        )
      : document;
  const activeLine = previewDocument?.lines.find((l) => l.id === baseActiveLine?.id) ?? baseActiveLine;
  const activeStyle = activeLine ? activeLine.style ?? previewDocument?.default_style ?? null : null;
  const rendering = renderJob?.status === "queued" || renderJob?.status === "running";

  return (
    <div className="mt-3 rounded border border-purple-200 bg-purple-50/50 p-4 dark:border-purple-900 dark:bg-purple-950/30">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold">{t(lang, "subtitle_studio")}</h4>
        <button type="button" className="text-xs text-neutral-500 hover:underline" onClick={onClose}>
          {t(lang, "close")}
        </button>
      </div>

      {loading && <p className="text-sm text-neutral-500">{t(lang, "loading")}</p>}
      {error && <div className="mb-3 rounded bg-red-100 p-2 text-xs text-red-700 dark:bg-red-900 dark:text-red-100">{error}</div>}

      {!loading && document && (
        <>
          {needsRebuild ? (
            <div className="mb-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950">
              <p>{t(lang, "subtitle_needs_rebuild")}</p>
              <button
                type="button"
                className="mt-2 rounded bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
                onClick={handleRender}
                disabled={rendering}
              >
                {rendering ? t(lang, "subtitle_rendering") : t(lang, "subtitle_render_now")}
              </button>
            </div>
          ) : (
            renderedVideoPath && (
              <div className="mb-3">
                <div ref={containerRef} className="relative mx-auto max-h-80 w-fit overflow-hidden rounded bg-black">
                  <video
                    ref={videoRef}
                    controls
                    className="max-h-80"
                    src={convertFileSrc(renderedVideoPath)}
                    onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                  />
                  {activeLine && activeStyle && scale > 0 && (
                    <div style={buildOverlayStyle(activeStyle, scale)}>{activeLine.text}</div>
                  )}
                </div>
                <p className="mt-1 text-center text-xs text-neutral-500">{t(lang, "subtitle_preview_approximate")}</p>
              </div>
            )
          )}

          <div className="max-h-64 space-y-2 overflow-y-auto rounded border border-neutral-200 p-2 dark:border-neutral-800">
            {document.lines.length === 0 && <p className="text-sm text-neutral-500">{t(lang, "subtitle_no_lines")}</p>}
            {document.lines.map((line, index) => (
              <div key={line.id} className="rounded border border-neutral-200 p-2 text-sm dark:border-neutral-800">
                <div className="mb-1 flex items-center gap-2 text-xs text-neutral-500">
                  <input
                    type="checkbox"
                    checked={selectedLineIds.has(line.id)}
                    onChange={() => toggleLineSelected(line.id)}
                    title={t(lang, "style_scope_selected_lines")}
                  />
                  <button type="button" className="text-purple-600 hover:underline dark:text-purple-400" onClick={() => handleJumpTo(line)}>
                    {formatTime(line.start)}
                  </button>
                  <input
                    type="number"
                    step={0.1}
                    className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
                    value={line.start}
                    onChange={(e) => handleTimingChange(line.id, "start", Number(e.target.value))}
                  />
                  <span>-</span>
                  <input
                    type="number"
                    step={0.1}
                    className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
                    value={line.end}
                    onChange={(e) => handleTimingChange(line.id, "end", Number(e.target.value))}
                  />
                  <span>{formatTime(line.end)}</span>
                </div>
                <input
                  className="w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-800"
                  value={line.text}
                  onChange={(e) => handleTextChange(line.id, e.target.value)}
                />
                <div className="mt-1 flex gap-2 text-xs">
                  <button type="button" className="text-neutral-500 hover:underline" onClick={() => handleSplit(line.id)}>
                    {t(lang, "subtitle_split")}
                  </button>
                  {index < document.lines.length - 1 && (
                    <button type="button" className="text-neutral-500 hover:underline" onClick={() => handleMergeWithNext(line.id)}>
                      {t(lang, "subtitle_merge_next")}
                    </button>
                  )}
                  <button type="button" className="text-red-600 hover:underline dark:text-red-400" onClick={() => handleDelete(line.id)}>
                    {t(lang, "subtitle_delete")}
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
              onClick={handleAddLine}
            >
              {t(lang, "subtitle_add_line")}
            </button>
            <button
              type="button"
              className={`rounded border px-3 py-1.5 text-sm ${
                showStyleEditor
                  ? "border-purple-600 bg-purple-600 text-white"
                  : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
              }`}
              onClick={() => (showStyleEditor ? closeStyleEditor() : openStyleEditor())}
            >
              {t(lang, "subtitle_style_button")}
            </button>
            <button
              type="button"
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
              onClick={handleSave}
              disabled={!dirty || saving}
            >
              {saving ? t(lang, "subtitle_saving") : t(lang, "subtitle_save")}
            </button>
            {saved && <span className="text-xs text-green-600 dark:text-green-400">{t(lang, "subtitle_saved")}</span>}
            {!needsRebuild && (
              <button
                type="button"
                className="rounded bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
                onClick={handleRender}
                disabled={rendering}
              >
                {rendering ? t(lang, "subtitle_rendering") : t(lang, "subtitle_render")}
              </button>
            )}
            {rendering && (
              <span className="text-xs text-neutral-500">
                {renderJob?.current_step ?? ""} ({renderJob?.progress.toFixed(0)}%)
              </span>
            )}
          </div>
          {renderJob?.status === "completed" && !rendering && (
            <p className="mt-1 text-xs text-green-600 dark:text-green-400">{t(lang, "subtitle_render_done")}</p>
          )}
          {renderError && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{renderError}</p>}

          {showStyleEditor && draftStyle && (
            <SubtitleStyleEditor
              lang={lang}
              style={draftStyle}
              scope={styleScope}
              selectedCount={selectedLineIds.size}
              hasActiveLine={!!baseActiveLine}
              onScopeChange={setStyleScope}
              onChange={setDraftStyle}
              onApply={handleApplyStyle}
              onCancel={closeStyleEditor}
              applying={applying}
            />
          )}
        </>
      )}
    </div>
  );
}
