#!/usr/bin/env bash
# Génère les dossiers Android / iOS puis applique les réglages de l'application.
set -euo pipefail
cd "$(dirname "$0")/.."
flutter create --org com.asvind --project-name iptv_player --platforms android,ios --no-pub .
rm -f test/widget_test.dart
python3 tool/patch_platforms.py
flutter pub get
dart run flutter_launcher_icons
