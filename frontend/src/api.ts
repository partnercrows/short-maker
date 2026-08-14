import { fetch as tauriFetch } from "@tauri-apps/plugin-http";

// The webview loads over https://tauri.localhost in a packaged build, and
// browsers block a plain http:// fetch from an https:// page as mixed
// content -- regardless of CORS. @tauri-apps/plugin-http routes the request
// through Rust instead of the webview's own network stack, sidestepping
// both that and CORS entirely.
const API_BASE = "http://127.0.0.1:8000";

let cachedToken: string | null = null;

async function getToken(): Promise<string> {
  if (cachedToken) return cachedToken;
  const res = await tauriFetch(`${API_BASE}/dev/session-token`);
  const data = await res.json();
  cachedToken = data.token;
  return cachedToken!;
}

const DEFAULT_TIMEOUT_MS = 60_000;

async function request<T>(path: string, options: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const token = await getToken();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  // A FormData body (image upload) needs the browser/runtime to set its own
  // multipart boundary in Content-Type -- forcing application/json here
  // would break the request.
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  try {
    const res = await tauriFetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        Authorization: `Bearer ${token}`,
        ...options.headers,
      },
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${body}`);
    }
    if (res.status === 204) return undefined as T;
    return res.json();
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s: ${path}`);
    }
    throw e;
  } finally {
    clearTimeout(timeout);
  }
}

export interface Project {
  id: string;
  name: string;
  source_video_path: string;
  source_duration: number | null;
  source_resolution: string | null;
  status: string;
  created_at: string;
}

export interface Job {
  id: string;
  project_id: string | null;
  type: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  current_step: string | null;
  error: string | null;
  started_at: string | null;
}

export interface Clip {
  id: string;
  project_id: string;
  start_time: number;
  end_time: number;
  duration: number;
  score: number | null;
  analysis_json: string | null;
  video_path: string | null;
  subtitle_path: string | null;
  status: string;
}

export interface ProviderConfig {
  provider_type: string;
  model: string;
  api_key: string;
  base_url?: string;
}

export interface ProviderCredentials {
  provider_type: string;
  api_key: string;
  base_url?: string;
}

export interface ConnectionTestResult {
  ok: boolean;
  detail: string;
}

export interface ModelInfo {
  id: string;
  display_name: string;
}

export function testProviderConnection(creds: ProviderCredentials): Promise<ConnectionTestResult> {
  return request("/ai-providers/test-connection", { method: "POST", body: JSON.stringify(creds) });
}

export function listProviderModels(creds: ProviderCredentials): Promise<ModelInfo[]> {
  return request("/ai-providers/models", { method: "POST", body: JSON.stringify(creds) }, 20_000);
}

export function createProject(name: string, sourceVideoPath: string): Promise<Project> {
  // Longer timeout: this copies the source video into project storage server-side,
  // which can take a while for a large file.
  return request(
    "/projects",
    { method: "POST", body: JSON.stringify({ name, source_video_path: sourceVideoPath }) },
    10 * 60_000,
  );
}

export function analyzeProject(
  projectId: string,
  provider: ProviderConfig,
  numClips: number | null,
  useGpu: boolean,
): Promise<Job> {
  return request(`/projects/${projectId}/analyze`, {
    method: "POST",
    body: JSON.stringify({ provider, num_clips: numClips, use_gpu: useGpu }),
  });
}

export function listProjects(): Promise<Project[]> {
  return request("/projects");
}

export interface SystemCapabilities {
  gpu_name: string | null;
  cuda_device_count: number;
  gpu_transcription_ready: boolean;
  detail: string;
}

export function getCapabilities(): Promise<SystemCapabilities> {
  return request("/system/capabilities");
}

export interface GpuPackStatus {
  installed: boolean;
}

export function getGpuPackStatus(): Promise<GpuPackStatus> {
  return request("/system/gpu-pack");
}

export function downloadGpuPack(): Promise<Job> {
  return request("/system/gpu-pack/download", { method: "POST" });
}

export function listClips(projectId: string): Promise<Clip[]> {
  return request(`/clips?project_id=${projectId}`);
}

export function generateClip(clipId: string, includeSubtitle: boolean, outputFolder?: string): Promise<Job> {
  return request(`/clips/${clipId}/generate`, {
    method: "POST",
    body: JSON.stringify({ include_subtitle: includeSubtitle, output_folder: outputFolder || undefined }),
  });
}

export function copyClipTo(clipId: string, destinationFolder: string): Promise<Job> {
  return request(`/clips/${clipId}/copy-to`, {
    method: "POST",
    body: JSON.stringify({ destination_folder: destinationFolder }),
  });
}

export interface IntroFrame {
  enabled: boolean;
  source: "captured" | "uploaded";
  source_timestamp: number | null;
  duration_seconds: number;
  created_at: string;
}

export interface IntroFrameResponse {
  intro: IntroFrame;
  image_path: string | null;
}

export function getIntroFrame(clipId: string): Promise<IntroFrameResponse> {
  return request(`/clips/${clipId}/intro`);
}

export function updateIntroFrame(clipId: string, enabled: boolean, durationSeconds: number): Promise<IntroFrameResponse> {
  return request(`/clips/${clipId}/intro`, {
    method: "PUT",
    body: JSON.stringify({ enabled, duration_seconds: durationSeconds }),
  });
}

export function captureIntroFrame(clipId: string, timestamp: number, durationSeconds: number): Promise<IntroFrameResponse> {
  return request(`/clips/${clipId}/intro/capture`, {
    method: "POST",
    body: JSON.stringify({ timestamp, duration_seconds: durationSeconds }),
  });
}

export function uploadIntroFrame(clipId: string, file: File, durationSeconds: number): Promise<IntroFrameResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("duration_seconds", String(durationSeconds));
  return request(`/clips/${clipId}/intro/upload`, { method: "POST", body: form });
}

export interface TitleOption {
  title: string;
  score: number;
}

export interface SocialKit {
  id: string;
  clip_id: string;
  platform: string;
  titles_json: string | null;
  description: string | null;
  hashtags: string | null;
  thumbnail_idea: string | null;
  thumbnail_prompt: string | null;
  created_at: string;
  updated_at: string;
}

export function getSocialKits(clipId: string): Promise<SocialKit[]> {
  return request(`/social-kit/${clipId}`);
}

export function generateSocialKit(clipId: string, platform: string, provider: ProviderConfig): Promise<SocialKit> {
  return request(`/social-kit/${clipId}/generate`, { method: "POST", body: JSON.stringify({ platform, provider }) }, 60_000);
}

export function regenerateSocialKit(clipId: string, platform: string, provider: ProviderConfig): Promise<SocialKit> {
  return request(`/social-kit/${clipId}/regenerate`, { method: "POST", body: JSON.stringify({ platform, provider }) }, 60_000);
}

export function getJob(jobId: string): Promise<Job> {
  return request(`/jobs/${jobId}`);
}

export function listJobs(projectId: string): Promise<Job[]> {
  return request(`/jobs?project_id=${projectId}`);
}

export function cancelJob(jobId: string): Promise<Job> {
  return request(`/jobs/${jobId}/cancel`, { method: "POST" });
}

export async function pollJob(jobId: string, onUpdate: (job: Job) => void): Promise<Job> {
  while (true) {
    const job = await getJob(jobId);
    onUpdate(job);
    if (job.status !== "queued" && job.status !== "running") return job;
    await new Promise((r) => setTimeout(r, 2000));
  }
}

// Subtitle Studio -- field names intentionally mirror the backend's
// Pydantic models verbatim (snake_case), same convention as ProviderConfig
// above, since these are serialized straight to/from the API with no
// client-side renaming layer.

export interface SubtitleWordStyleOverride {
  color: string | null;
  weight: number | null;
  background_color: string | null;
  glow: boolean | null;
}

export interface SubtitleWord {
  text: string;
  start: number;
  end: number;
  style: SubtitleWordStyleOverride | null;
}

export interface SubtitlePosition {
  x: number;
  y: number;
}

export interface SubtitleBackground {
  enabled: boolean;
  color: string;
  opacity: number;
  border_radius: number;
  padding: number;
}

export interface SubtitleStroke {
  enabled: boolean;
  color: string;
  width: number;
}

export interface SubtitleShadow {
  enabled: boolean;
  color: string;
  opacity: number;
  blur: number;
  offset_x: number;
  offset_y: number;
}

export interface SubtitleGlow {
  enabled: boolean;
  color: string;
  opacity: number;
  blur: number;
  spread: number;
}

export interface SubtitleStyle {
  preset: string | null;
  font_family: string;
  font_size: number;
  font_weight: number;
  text_color: string;
  position: SubtitlePosition;
  alignment: "left" | "center" | "right";
  background: SubtitleBackground;
  stroke: SubtitleStroke;
  shadow: SubtitleShadow;
  glow: SubtitleGlow;
  uppercase: boolean;
  italic: boolean;
  display_mode: "sentence" | "karaoke";
  highlight_color: string;
}

export interface SubtitleDocumentLine {
  id: string;
  start: number;
  end: number;
  text: string;
  words: SubtitleWord[] | null;
  style: SubtitleStyle | null;
}

export interface SubtitleDocument {
  version: number;
  clip_id: string;
  default_style: SubtitleStyle;
  lines: SubtitleDocumentLine[];
  updated_at: string;
}

export interface SubtitleDocumentResponse {
  document: SubtitleDocument;
  needs_rebuild: boolean;
  rendered_video_path: string | null;
}

export function getSubtitleDocument(clipId: string): Promise<SubtitleDocumentResponse> {
  return request(`/subtitles/${clipId}`);
}

export function saveSubtitleDocument(clipId: string, document: SubtitleDocument): Promise<SubtitleDocument> {
  return request(`/subtitles/${clipId}/document`, { method: "PUT", body: JSON.stringify(document) });
}

export interface ApplyStyleRequest {
  scope: "line" | "lines" | "clip";
  line_ids?: string[];
  style: SubtitleStyle;
}

export function applySubtitleStyle(clipId: string, req: ApplyStyleRequest): Promise<SubtitleDocument> {
  return request(`/subtitles/${clipId}/style`, { method: "POST", body: JSON.stringify(req) });
}

export function renderSubtitleJob(clipId: string): Promise<Job> {
  return request(`/subtitles/${clipId}/render`, { method: "POST" });
}
