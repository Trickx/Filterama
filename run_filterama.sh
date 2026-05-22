#!/usr/bin/env bash
# Launcher to open the built Filterama.app so macOS shows the correct app name and icon
APP_PATH="$(pwd)/dist/Filterama.app"
if [ ! -d "$APP_PATH" ]; then
  echo "App not found at $APP_PATH"
  exit 1
fi
open -a "$APP_PATH"
