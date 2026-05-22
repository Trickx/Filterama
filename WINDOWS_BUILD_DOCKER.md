# Windows Build mit Docker

Dieses Projekt kann auf macOS/Linux in einem Docker-Container als Windows-Executable gebaut werden.

## Voraussetzungen

- Docker Desktop (oder Docker Engine) ist installiert und laeuft.
- Genug freier Speicher fuer Image + Build-Artefakte.

## Build starten

```bash
./build_windows_docker.sh
```

Das Skript:

1. baut ein Builder-Image aus `docker/windows/Dockerfile`
2. fuehrt PyInstaller im Windows-Python (Wine) auf `src/Filterama.py` aus
3. legt das Ergebnis in `dist/Filterama/Filterama.exe` ab

## Hinweise

- Die Build-Artefakte liegen in `build/` und `dist/` im Projektordner.
- Wenn ein komplett sauberer Build gewuenscht ist, loesche vorher `build/` und `dist/`.
- Fuer CLI statt GUI kann `--windowed` im Skript entfernt werden.
