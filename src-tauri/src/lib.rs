use std::sync::Mutex;

use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the backend sidecar's child handle so it can be killed when the app
/// exits -- otherwise it would keep running as an orphaned process (the user
/// previously had to run it by hand and remember to stop it themselves).
struct BackendProcess(Mutex<Option<CommandChild>>);

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
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      let (mut receiver, child) = app
        .shell()
        .sidecar("short-maker-backend")
        .expect("failed to create backend sidecar command")
        .spawn()
        .expect("failed to spawn backend sidecar");

      *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);

      // Forward the backend's own stdout/stderr into this app's log stream
      // instead of letting it vanish silently.
      tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
          match event {
            CommandEvent::Stdout(line) => log::info!("[backend] {}", String::from_utf8_lossy(&line)),
            CommandEvent::Stderr(line) => log::info!("[backend] {}", String::from_utf8_lossy(&line)),
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
