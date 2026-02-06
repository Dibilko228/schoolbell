Android APK for SchoolBell

This folder contains the Kivy/KivyMD port of the SchoolBell desktop app for Android.

Architecture:
- Tab-based UI: Clock (time + lesson display), Recordings (start/stop/list), Schedule (view + edit), Settings.
- MDTabs for navigation.
- Config stored in ~/SchoolBell/config.json on device.
- Recordings stored in ~/SchoolBell/recordings/ (WAV format).

Current status:
- UI scaffolding complete (4 tabs).
- Recording: TODO (requires pyjnius + android.media.MediaRecorder).
- Playback: TODO (requires Android AudioTrack or MediaPlayer).
- Schedule saving: partial (read from config).

Building the APK:
Buildozer requires Linux. On Windows, use WSL2 or a Linux VM:

```bash
# Inside WSL/Linux with Python 3.11+
pip install buildozer
cd android_port
buildozer -v android debug   # produces .apk in bin/
```

Requirements:
- Android SDK (API 21+)
- Android NDK
- Java JDK 11+
- See Buildozer docs for full setup: https://buildozer.readthedocs.io/

Next steps:
1. Implement recording via pyjnius (MediaRecorder API).
2. Implement playback via android.media.AudioTrack.
3. Add schedule playback in background service.
4. Test on Android device or emulator.
5. Sign APK for production release.

Optional: Use GitHub Actions CI to automate APK builds.