import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";

let permissionChecked = false;

async function ensurePermission(): Promise<boolean> {
  if (await isPermissionGranted()) return true;
  if (permissionChecked) return false;
  permissionChecked = true;
  const result = await requestPermission();
  return result === "granted";
}

export async function notify(title: string, body: string): Promise<void> {
  try {
    if (await ensurePermission()) {
      sendNotification({ title, body });
    }
  } catch {
    // Notifications are a nice-to-have; never let a failure here break the job flow.
  }
}
