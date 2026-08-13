export interface ActiveJobStatus {
  label: string;
  progress: number;
  step: string | null;
}

type Listener = () => void;

const listeners = new Set<Listener>();
let jobs: Record<string, ActiveJobStatus> = {};
let snapshot: ActiveJobStatus[] = [];

function notify() {
  snapshot = Object.values(jobs);
  listeners.forEach((l) => l());
}

export function setActiveJob(id: string, status: ActiveJobStatus | null) {
  if (status === null) {
    if (!(id in jobs)) return;
    const rest = { ...jobs };
    delete rest[id];
    jobs = rest;
  } else {
    jobs = { ...jobs, [id]: status };
  }
  notify();
}

export function getActiveJobs(): ActiveJobStatus[] {
  return snapshot;
}

export function subscribeActiveJobs(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
