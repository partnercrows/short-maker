import type { SubtitleStyle } from "./api";

// Mirrors backend/app/pipeline/subtitle/models.py's PRESETS exactly -- kept
// as a frontend constant (not fetched) since these are static, named style
// shortcuts with no server-side logic behind them.

export const SUBTITLE_PRESETS: Record<string, SubtitleStyle> = {
  penyorot: {
    preset: "penyorot",
    font_family: "Arial",
    font_size: 52,
    font_weight: 800,
    text_color: "#FFEE00",
    alignment: "center",
    position: { x: 360, y: 1150 },
    background: { enabled: true, color: "#000000", opacity: 0.7, border_radius: 10, padding: 14 },
    stroke: { enabled: true, color: "#000000", width: 3 },
    shadow: { enabled: false, color: "#000000", opacity: 0.5, blur: 4, offset_x: 2, offset_y: 2 },
    glow: { enabled: false, color: "#FFFFFF", opacity: 0.8, blur: 8, spread: 2 },
  },
  editorial: {
    preset: "editorial",
    font_family: "Georgia",
    font_size: 46,
    font_weight: 500,
    text_color: "#FFFFFF",
    alignment: "center",
    position: { x: 360, y: 1150 },
    background: { enabled: false, color: "#000000", opacity: 0.6, border_radius: 8, padding: 12 },
    stroke: { enabled: true, color: "#000000", width: 2 },
    shadow: { enabled: true, color: "#000000", opacity: 0.5, blur: 4, offset_x: 1, offset_y: 1 },
    glow: { enabled: false, color: "#FFFFFF", opacity: 0.8, blur: 8, spread: 2 },
  },
  bold_pop: {
    preset: "bold_pop",
    font_family: "Arial",
    font_size: 56,
    font_weight: 900,
    text_color: "#FFFFFF",
    alignment: "center",
    position: { x: 360, y: 1000 },
    background: { enabled: false, color: "#000000", opacity: 0.6, border_radius: 8, padding: 12 },
    stroke: { enabled: true, color: "#FF2D55", width: 4 },
    shadow: { enabled: false, color: "#000000", opacity: 0.5, blur: 4, offset_x: 2, offset_y: 2 },
    glow: { enabled: true, color: "#FF2D55", opacity: 0.6, blur: 10, spread: 3 },
  },
  newsroom: {
    preset: "newsroom",
    font_family: "Arial",
    font_size: 42,
    font_weight: 600,
    text_color: "#FFFFFF",
    alignment: "left",
    position: { x: 60, y: 1180 },
    background: { enabled: true, color: "#CC0000", opacity: 1.0, border_radius: 0, padding: 10 },
    stroke: { enabled: false, color: "#000000", width: 2 },
    shadow: { enabled: false, color: "#000000", opacity: 0.5, blur: 4, offset_x: 2, offset_y: 2 },
    glow: { enabled: false, color: "#FFFFFF", opacity: 0.8, blur: 8, spread: 2 },
  },
};

export const PRESET_LABELS: Record<string, string> = {
  penyorot: "Penyorot",
  editorial: "Editorial",
  bold_pop: "Bold Pop",
  newsroom: "Newsroom",
};

export const CANVAS_WIDTH = 720;
export const CANVAS_HEIGHT = 1280;
