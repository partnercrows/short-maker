import { invoke } from "@tauri-apps/api/core";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

export type UpdateCheckResult =
  | { status: "up-to-date" }
  | { status: "available"; version: string; body: string; install: () => Promise<void> }
  | { status: "error"; message: string };

export async function checkForUpdate(): Promise<UpdateCheckResult> {
  try {
    const update = await check();
    if (!update) return { status: "up-to-date" };
    return {
      status: "available",
      version: update.version,
      body: update.body ?? "",
      install: async () => {
        // The installer the updater runs next needs to overwrite
        // short-maker-backend.exe -- stop it first so that file isn't
        // still locked by this same running app when the installer gets to it.
        await invoke("stop_backend_sidecar");
        await update.downloadAndInstall();
        await relaunch();
      },
    };
  } catch (e) {
    return { status: "error", message: String(e) };
  }
}
