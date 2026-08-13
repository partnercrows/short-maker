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
  try {
    const res = await tauriFetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
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

export function listClips(projectId: string): Promise<Clip[]> {
  return request(`/clips?project_id=${projectId}`);
}

export function generateClip(clipId: string, includeSubtitle: boolean, outputFolder?: string): Promise<Job> {
  return request(`/clips/${clipId}/generate`, {
    method: "POST",
    body: JSON.stringify({ include_subtitle: includeSubtitle, output_folder: outputFolder || undefined }),
  });
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
