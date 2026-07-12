// AIPTP desktop shell: supervises the bundled server sidecar and shows the
// web UI once it is healthy. Desktop mode binds to 127.0.0.1 with auth
// disabled (PRD §4 Desktop Mode).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::time::Duration;
use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

const SERVER_URL: &str = "http://127.0.0.1:8420";

fn data_dir(app: &tauri::AppHandle) -> std::path::PathBuf {
    app.path()
        .app_data_dir()
        .expect("no app data dir")
        .join("data")
}

async fn wait_healthy() -> bool {
    for _ in 0..120 {
        if let Ok(resp) = reqwest_get(&format!("{SERVER_URL}/api/v1/health")).await {
            if resp {
                return true;
            }
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    false
}

async fn reqwest_get(url: &str) -> Result<bool, ()> {
    // std-only probe to avoid a heavyweight HTTP dependency
    use std::io::{Read, Write};
    let addr = "127.0.0.1:8420";
    let path = url.split("8420").nth(1).unwrap_or("/").to_string();
    tokio::task::spawn_blocking(move || {
        let mut stream = std::net::TcpStream::connect_timeout(
            &addr.parse().map_err(|_| ())?,
            Duration::from_millis(400),
        )
        .map_err(|_| ())?;
        stream
            .write_all(format!("GET {path} HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n").as_bytes())
            .map_err(|_| ())?;
        let mut buf = String::new();
        stream.read_to_string(&mut buf).map_err(|_| ())?;
        Ok(buf.contains("200 OK"))
    })
    .await
    .map_err(|_| ())?
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let dir = data_dir(&handle);
            std::fs::create_dir_all(&dir).ok();

            let sidecar = handle
                .shell()
                .sidecar("aiptp-server")
                .expect("sidecar missing")
                .env("AIPTP_HOST", "127.0.0.1")
                .env("AIPTP_PORT", "8420")
                .env("AIPTP_AUTH", "disabled")
                .env("AIPTP_DATA_DIR", dir.to_string_lossy().to_string());
            let (mut rx, _child) = sidecar.spawn().expect("failed to start server");

            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    if let CommandEvent::Stderr(line) = event {
                        eprintln!("[server] {}", String::from_utf8_lossy(&line));
                    }
                }
            });

            let win = app.get_webview_window("main").expect("no main window");
            tauri::async_runtime::spawn(async move {
                if wait_healthy().await {
                    let _ = win.eval(&format!("window.location.replace('{SERVER_URL}')"));
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running AIPTP desktop");
}
