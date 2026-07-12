# AIPTP Desktop Shell (Tauri 2)

Wraps the AIPTP server + web UI in a native window with installers for
Windows 10/11, macOS (Intel + Apple Silicon), and Linux (deb/rpm/AppImage).

**Status: scaffold.** The shell launches the bundled server binary as a
sidecar on `127.0.0.1:8420` and opens the UI. Installer builds run in CI
(`.github/workflows/desktop.yml`) via PyInstaller (server sidecar) +
`tauri-action`; they are not yet exercised in the development container, so
treat the first CI run as the real test.

## Local development

```bash
# 1. Freeze the server into a sidecar binary (once per backend change)
pip install pyinstaller
pyinstaller --onefile --name aiptp-server backend/aiptp/main.py \
  --collect-all aiptp --hidden-import uvicorn.logging
mv dist/aiptp-server desktop/src-tauri/binaries/aiptp-server-$(rustc -vV | grep host | cut -d' ' -f2)

# 2. Run the shell
cd desktop && cargo tauri dev
```

The production window loads `http://127.0.0.1:8420` served by the sidecar;
`npm run build` output must exist in `frontend/dist` before freezing.
