import type { ReactNode } from "react";
import { t, type Language } from "./i18n";
import { PRESET_LABELS, SUBTITLE_PRESETS } from "./subtitlePresets";
import type { SubtitleStyle } from "./api";

export type StyleScope = "line" | "lines" | "clip";

interface Props {
  lang: Language;
  style: SubtitleStyle;
  scope: StyleScope;
  selectedCount: number;
  hasActiveLine: boolean;
  onScopeChange: (scope: StyleScope) => void;
  onChange: (style: SubtitleStyle) => void;
  onApply: () => void;
  onCancel: () => void;
  applying: boolean;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="text-neutral-500">{label}</span>
      {children}
    </label>
  );
}

export default function SubtitleStyleEditor({
  lang,
  style,
  scope,
  selectedCount,
  hasActiveLine,
  onScopeChange,
  onChange,
  onApply,
  onCancel,
  applying,
}: Props) {
  function set<K extends keyof SubtitleStyle>(key: K, value: SubtitleStyle[K]) {
    onChange({ ...style, [key]: value });
  }
  function setNested<K extends keyof SubtitleStyle>(key: K, patch: Partial<SubtitleStyle[K]>) {
    onChange({ ...style, [key]: { ...(style[key] as object), ...patch } });
  }

  return (
    <div className="mt-3 space-y-3 rounded border border-neutral-200 bg-white p-3 text-sm dark:border-neutral-800 dark:bg-neutral-900">
      <div>
        <div className="mb-1 text-xs font-medium text-neutral-500">{t(lang, "style_presets")}</div>
        <div className="flex flex-wrap gap-2">
          {Object.keys(SUBTITLE_PRESETS).map((key) => (
            <button
              key={key}
              type="button"
              className={`rounded px-2 py-1 text-xs ${
                style.preset === key
                  ? "bg-purple-600 text-white"
                  : "border border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
              }`}
              onClick={() => onChange(SUBTITLE_PRESETS[key])}
            >
              {PRESET_LABELS[key]}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-1 text-xs font-medium text-neutral-500">{t(lang, "style_apply_to")}</div>
        <div className="space-y-1 text-xs">
          <label className="flex items-center gap-2">
            <input type="radio" checked={scope === "line"} disabled={!hasActiveLine} onChange={() => onScopeChange("line")} />
            {t(lang, "style_scope_this_line")}
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              checked={scope === "lines"}
              disabled={selectedCount === 0}
              onChange={() => onScopeChange("lines")}
            />
            {t(lang, "style_scope_selected_lines")} ({selectedCount})
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={scope === "clip"} onChange={() => onScopeChange("clip")} />
            {t(lang, "style_scope_all_lines")}
          </label>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        <Field label={t(lang, "style_font_family")}>
          <input
            className="w-28 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
            value={style.font_family}
            onChange={(e) => set("font_family", e.target.value)}
          />
        </Field>
        <Field label={t(lang, "style_font_size")}>
          <input
            type="number"
            className="w-20 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
            value={style.font_size}
            onChange={(e) => set("font_size", Number(e.target.value))}
          />
        </Field>
        <Field label={t(lang, "style_font_weight")}>
          <select
            className="w-20 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
            value={style.font_weight}
            onChange={(e) => set("font_weight", Number(e.target.value))}
          >
            {[400, 500, 600, 700, 800, 900].map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t(lang, "style_alignment")}>
          <div className="flex gap-1">
            {(["left", "center", "right"] as const).map((a) => (
              <button
                key={a}
                type="button"
                className={`rounded px-1.5 py-0.5 text-xs ${
                  style.alignment === a ? "bg-purple-600 text-white" : "border border-neutral-300 dark:border-neutral-700"
                }`}
                onClick={() => set("alignment", a)}
              >
                {a === "left" ? "⟵" : a === "center" ? "↔" : "⟶"}
              </button>
            ))}
          </div>
        </Field>
        <Field label={t(lang, "style_text_color")}>
          <input type="color" value={style.text_color} onChange={(e) => set("text_color", e.target.value)} />
        </Field>
        <Field label={t(lang, "style_position_x")}>
          <input
            type="number"
            className="w-20 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
            value={style.position.x}
            onChange={(e) => setNested("position", { x: Number(e.target.value) })}
          />
        </Field>
        <Field label={t(lang, "style_position_y")}>
          <input
            type="number"
            className="w-20 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
            value={style.position.y}
            onChange={(e) => setNested("position", { y: Number(e.target.value) })}
          />
        </Field>
      </div>
      <div className="flex gap-2">
        {[
          { label: t(lang, "style_position_preset_top"), y: 160 },
          { label: t(lang, "style_position_preset_center"), y: 640 },
          { label: t(lang, "style_position_preset_bottom"), y: 1150 },
        ].map((p) => (
          <button
            key={p.label}
            type="button"
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
            onClick={() => setNested("position", { y: p.y })}
          >
            {p.label}
          </button>
        ))}
      </div>

      <fieldset className="rounded border border-neutral-200 p-2 dark:border-neutral-800">
        <legend className="px-1 text-xs font-medium text-neutral-500">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={style.background.enabled} onChange={(e) => setNested("background", { enabled: e.target.checked })} />
            {t(lang, "style_background")}
          </label>
        </legend>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <Field label={t(lang, "style_color")}>
            <input type="color" value={style.background.color} onChange={(e) => setNested("background", { color: e.target.value })} />
          </Field>
          <Field label={t(lang, "style_opacity")}>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={style.background.opacity}
              onChange={(e) => setNested("background", { opacity: Number(e.target.value) })}
            />
          </Field>
          <Field label={t(lang, "style_border_radius")}>
            <input
              type="number"
              className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
              value={style.background.border_radius}
              onChange={(e) => setNested("background", { border_radius: Number(e.target.value) })}
            />
          </Field>
          <Field label={t(lang, "style_padding")}>
            <input
              type="number"
              className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
              value={style.background.padding}
              onChange={(e) => setNested("background", { padding: Number(e.target.value) })}
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded border border-neutral-200 p-2 dark:border-neutral-800">
        <legend className="px-1 text-xs font-medium text-neutral-500">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={style.stroke.enabled} onChange={(e) => setNested("stroke", { enabled: e.target.checked })} />
            {t(lang, "style_stroke")}
          </label>
        </legend>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <Field label={t(lang, "style_color")}>
            <input type="color" value={style.stroke.color} onChange={(e) => setNested("stroke", { color: e.target.value })} />
          </Field>
          <Field label={t(lang, "style_width")}>
            <input
              type="number"
              className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
              value={style.stroke.width}
              onChange={(e) => setNested("stroke", { width: Number(e.target.value) })}
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded border border-neutral-200 p-2 dark:border-neutral-800">
        <legend className="px-1 text-xs font-medium text-neutral-500">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={style.shadow.enabled} onChange={(e) => setNested("shadow", { enabled: e.target.checked })} />
            {t(lang, "style_shadow")}
          </label>
        </legend>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <Field label={t(lang, "style_color")}>
            <input type="color" value={style.shadow.color} onChange={(e) => setNested("shadow", { color: e.target.value })} />
          </Field>
          <Field label={t(lang, "style_opacity")}>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={style.shadow.opacity}
              onChange={(e) => setNested("shadow", { opacity: Number(e.target.value) })}
            />
          </Field>
          <Field label={t(lang, "style_blur")}>
            <input
              type="number"
              className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
              value={style.shadow.blur}
              onChange={(e) => setNested("shadow", { blur: Number(e.target.value) })}
            />
          </Field>
          <Field label={t(lang, "style_offset_x")}>
            <input
              type="number"
              className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
              value={style.shadow.offset_x}
              onChange={(e) => setNested("shadow", { offset_x: Number(e.target.value) })}
            />
          </Field>
          <Field label={t(lang, "style_offset_y")}>
            <input
              type="number"
              className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
              value={style.shadow.offset_y}
              onChange={(e) => setNested("shadow", { offset_y: Number(e.target.value) })}
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded border border-neutral-200 p-2 dark:border-neutral-800">
        <legend className="px-1 text-xs font-medium text-neutral-500">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={style.glow.enabled} onChange={(e) => setNested("glow", { enabled: e.target.checked })} />
            {t(lang, "style_glow")}
          </label>
        </legend>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <Field label={t(lang, "style_color")}>
            <input type="color" value={style.glow.color} onChange={(e) => setNested("glow", { color: e.target.value })} />
          </Field>
          <Field label={t(lang, "style_opacity")}>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={style.glow.opacity}
              onChange={(e) => setNested("glow", { opacity: Number(e.target.value) })}
            />
          </Field>
          <Field label={t(lang, "style_blur")}>
            <input
              type="number"
              className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
              value={style.glow.blur}
              onChange={(e) => setNested("glow", { blur: Number(e.target.value) })}
            />
          </Field>
          <Field label={t(lang, "style_spread")}>
            <input
              type="number"
              className="w-16 rounded border border-neutral-300 bg-white px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
              value={style.glow.spread}
              onChange={(e) => setNested("glow", { spread: Number(e.target.value) })}
            />
          </Field>
        </div>
      </fieldset>

      <div className="flex gap-2">
        <button
          type="button"
          className="rounded bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
          onClick={onApply}
          disabled={applying}
        >
          {applying ? t(lang, "style_applying") : t(lang, "style_apply")}
        </button>
        <button
          type="button"
          className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
          onClick={onCancel}
        >
          {t(lang, "cancel")}
        </button>
      </div>
    </div>
  );
}
