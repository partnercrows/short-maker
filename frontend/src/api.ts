const API_BASE = "http://127.0.0.1:8000";

let cachedToken: string | null = null;

async function getToken(): Promise<string> {
  if (cachedToken) return cachedToken;
  const res = await fetch(`${API_BASE}/dev/session-token`);
  const data = await res.json();
  cachedToken = data.token;
  return cachedToken!;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
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
}

export interface Project {
  id: string;
  name: string;
  source_video_path: string;
  source_duration: number | null;
  source_resolution: string | null;
  status: string;
}

export interface Job {
  id: string;
  project_id: string | null;
  type: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  current_step: string | null;
  error: string | null;
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

export function createProject(name: string, sourceVideoPath: string): Promise<Project> {
  return request("/projects", {
    method: "POST",
    body: JSON.stringify({ name, source_video_path: sourceVideoPath }),
  });
}

export function analyzeProject(projectId: string, provider: ProviderConfig, numClips: number | null): Promise<Job> {
  return request(`/projects/${projectId}/analyze`, {
    method: "POST",
    body: JSON.stringify({ provider, num_clips: numClips }),
  });
}

export function listClips(projectId: string): Promise<Clip[]> {
  return request(`/clips?project_id=${projectId}`);
}

export function generateClip(clipId: string, includeSubtitle: boolean): Promise<Job> {
  return request(`/clips/${clipId}/generate`, {
    method: "POST",
    body: JSON.stringify({ include_subtitle: includeSubtitle }),
  });
}

export function getJob(jobId: string): Promise<Job> {
  return request(`/jobs/${jobId}`);
}

export async function pollJob(jobId: string, onUpdate: (job: Job) => void): Promise<Job> {
  while (true) {
    const job = await getJob(jobId);
    onUpdate(job);
    if (job.status !== "queued" && job.status !== "running") return job;
    await new Promise((r) => setTimeout(r, 2000));
  }
}
