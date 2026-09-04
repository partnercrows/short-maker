use std::path::{Path, PathBuf};
use std::sync::Mutex;

use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the backend sidecar's child handle so it can be killed when the app
/// exits -- otherwise it would keep running as an orphaned process (the user
/// previously had to run it by hand and remember to stop it themselves).
struct BackendProcess(Mutex<Option<CommandChild>>);

/// The last thing the sidecar said before dying, so a backend that never
/// comes up can explain itself. Without this the frontend could only report
/// "the backend didn't start in time", which is a symptom, not a reason --
/// the actual message (a full disk stopping PyInstaller from unpacking, say)
/// went nowhere in a release build.
#[derive(Default)]
struct BackendStderr(Mutex<Vec<String>>);

const STDERR_LINES_KEPT: usize = 12;

/// A file only *our* sidecar's unpacked bundle contains -- used to tell our
/// leftover PyInstaller directories apart from any other app's before
/// deleting anything under the shared temp directory.
const BUNDLE_MARKER: &str = "app/pipeline/common/models/face_detection_yunet_2023mar.onnx";

/// The updater plugin's `downloadAndInstall()` launches the new
/// installer while this app (and its sidecar) is still fully running --
/// the installer then fails to overwrite short-maker-backend.exe because
/// our own sidecar still has that exact file open. The frontend calls this
/// right before `downloadAndInstall()` so the installer's target file is
/// already free by the time it runs, instead of racing it.
#[tauri::command]
fn stop_backend_sidecar(app_handle: tauri::AppHandle) {
  if let Some(child) = app_handle.state::<BackendProcess>().0.lock().unwrap().take() {
    let _ = child.kill();
  }
  kill_orphaned_backend_processes();
  sweep_stale_bundle_dirs();
}

/// What the sidecar printed before it stopped. The frontend asks for this
/// when its health-check poll times out, so the startup screen can show the
/// real failure instead of a generic timeout.
#[tauri::command]
fn backend_stderr(app_handle: tauri::AppHandle) -> Vec<String> {
  app_handle.state::<BackendStderr>().0.lock().unwrap().clone()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_notification::init())
    .plugin(tauri_plugin_updater::Builder::new().build())
    .plugin(tauri_plugin_process::init())
    .plugin(tauri_plugin_http::init())
    .plugin(tauri_plugin_shell::init())
    .manage(BackendProcess(Mutex::new(None)))
    .manage(BackendStderr::default())
    .invoke_handler(tauri::generate_handler![stop_backend_sidecar, backend_stderr])
    .setup(|app| {
      app.handle().plugin(
        tauri_plugin_log::Builder::default()
          .level(log::LevelFilter::Info)
          .build(),
      )?;

      // Before spawning: reclaim what previous runs left behind. The sidecar
      // needs a few hundred MB of free temp space to unpack into, and these
      // leftovers are exactly what eats it.
      sweep_stale_bundle_dirs();

      let (mut receiver, child) = app
        .shell()
        .sidecar("short-maker-backend")
        .expect("failed to create backend sidecar command")
        .spawn()
        .expect("failed to spawn backend sidecar");

      *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);

      // Forward the backend's own stdout/stderr into this app's log stream
      // instead of letting it vanish silently.
      let handle = app.handle().clone();
      tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
          match event {
            CommandEvent::Stdout(line) => log::info!("[backend] {}", String::from_utf8_lossy(&line)),
            CommandEvent::Stderr(line) => {
              let text = String::from_utf8_lossy(&line).trim_end().to_string();
              log::info!("[backend] {}", text);
              if !text.is_empty() {
                let state = handle.state::<BackendStderr>();
                let mut kept = state.0.lock().unwrap();
                if kept.len() == STDERR_LINES_KEPT {
                  kept.remove(0);
                }
                kept.push(text);
              }
            }
            CommandEvent::Error(message) => log::error!("[backend] {}", message),
            CommandEvent::Terminated(payload) => {
              log::error!("[backend] exited with {:?}", payload.code);
              let state = handle.state::<BackendStderr>();
              let mut kept = state.0.lock().unwrap();
              kept.push(format!("backend exited with code {:?}", payload.code));
            }
            _ => {}
          }
        }
      });

      Ok(())
    })
    .build(tauri::generate_context!())
    .expect("error while building tauri application")
    .run(|app_handle, event| {
      if let tauri::RunEvent::ExitRequested { .. } = event {
        if let Some(child) = app_handle.state::<BackendProcess>().0.lock().unwrap().take() {
          let _ = child.kill();
        }
        kill_orphaned_backend_processes();
        sweep_stale_bundle_dirs();
      }
    });
}

/// `child.kill()` above only terminates the sidecar process Tauri directly
/// spawned. A PyInstaller --onefile executable is a bootloader that
/// self-extracts into a temp dir and launches the *real* interpreter as its
/// own child process, which keeps running as an orphan when the bootloader
/// is killed rather than exiting with it. Sweep by image name as a
/// belt-and-suspenders cleanup so a closed app never leaves a backend
/// process (and its bound port) behind.
#[cfg(windows)]
fn kill_orphaned_backend_processes() {
  use std::os::windows::process::CommandExt;
  const CREATE_NO_WINDOW: u32 = 0x08000000;
  let _ = std::process::Command::new("taskkill")
    .args(["/F", "/IM", "short-maker-backend.exe", "/T"])
    .creation_flags(CREATE_NO_WINDOW)
    .status();
}

#[cfg(not(windows))]
fn kill_orphaned_backend_processes() {}

/// Deletes the `_MEIxxxxx` directories our sidecar unpacked itself into on
/// previous runs.
///
/// A PyInstaller onefile bootloader removes its own directory when it exits
/// normally -- but the cleanup above force-kills it, so it never gets the
/// chance, and every launch strands roughly 380 MB in the temp directory.
/// Left alone that fills the disk (a user hit 0 bytes free with 22 of these
/// stranded, 7.5 GB), at which point the sidecar can no longer unpack at all
/// and the app stops starting: the leak eventually kills the app itself.
///
/// Only directories that still contain `BUNDLE_MARKER` are touched, and
/// deletion is best-effort per directory -- the one belonging to a sidecar
/// that is currently running holds its files open, so it simply fails to
/// delete and is left alone.
fn sweep_stale_bundle_dirs() {
  // A *running* sidecar's directory is not stale, and deleting into it would
  // be worse than the leak: the files it has mapped (python312.dll and
  // friends) can't be removed, but the ones it merely reads later can, which
  // would break a second app instance mid-run. So sweep only when no backend
  // is alive anywhere on the machine.
  if backend_process_is_running() {
    return;
  }
  let Ok(entries) = std::fs::read_dir(std::env::temp_dir()) else {
    return;
  };
  for entry in entries.flatten() {
    let path = entry.path();
    if is_our_bundle_dir(&path) {
      let _ = std::fs::remove_dir_all(&path);
    }
  }
}

#[cfg(windows)]
fn backend_process_is_running() -> bool {
  use std::os::windows::process::CommandExt;
  const CREATE_NO_WINDOW: u32 = 0x08000000;
  let Ok(output) = std::process::Command::new("tasklist")
    .args(["/FI", "IMAGENAME eq short-maker-backend.exe", "/NH"])
    .creation_flags(CREATE_NO_WINDOW)
    .output()
  else {
    return true; // can't tell -- assume one is running and skip the sweep
  };
  String::from_utf8_lossy(&output.stdout).contains("short-maker-backend.exe")
}

#[cfg(not(windows))]
fn backend_process_is_running() -> bool {
  false
}

fn is_our_bundle_dir(path: &Path) -> bool {
  let is_mei_dir = path
    .file_name()
    .and_then(|name| name.to_str())
    .is_some_and(|name| name.starts_with("_MEI"));
  if !is_mei_dir || !path.is_dir() {
    return false;
  }
  PathBuf::from(path).join(BUNDLE_MARKER).is_file()
}

#[cfg(test)]
mod tests {
  use super::*;

  fn make_bundle_dir(root: &Path, name: &str, with_marker: bool) -> PathBuf {
    let dir = root.join(name);
    if with_marker {
      let marker = dir.join(BUNDLE_MARKER);
      std::fs::create_dir_all(marker.parent().unwrap()).unwrap();
      std::fs::write(marker, b"model").unwrap();
    } else {
      std::fs::create_dir_all(&dir).unwrap();
    }
    dir
  }

  #[test]
  fn recognises_only_our_own_leftover_bundles() {
    let root = std::env::temp_dir().join(format!("sm-sweep-test-{}", std::process::id()));
    std::fs::create_dir_all(&root).unwrap();

    let ours = make_bundle_dir(&root, "_MEI123456", true);
    let someone_elses = make_bundle_dir(&root, "_MEI999999", false);
    let unrelated = make_bundle_dir(&root, "some-other-temp-dir", true);

    assert!(is_our_bundle_dir(&ours));
    assert!(!is_our_bundle_dir(&someone_elses));
    assert!(!is_our_bundle_dir(&unrelated));

    std::fs::remove_dir_all(&root).unwrap();
  }
}
