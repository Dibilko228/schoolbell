# Building the SchoolBell APK

There are three ways to build the APK:

## Option 1: GitHub Actions (Recommended for Windows)

Push your code to GitHub and the APK will build automatically.

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/schoolbell.git
git push -u origin main
```

The workflow will:
- Run on every push
- Build the APK on Linux
- Upload artifact to Actions (visible in Releases)

**Artifact location**: GitHub Actions → Artifacts → `schoolbell-apk`

---

## Option 2: WSL2 Build (Windows)

If you have WSL2 installed:

```powershell
# In PowerShell, run:
.\build_apk.bat
```

This will:
1. Detect WSL2
2. Setup Android SDK/NDK (if not already done)
3. Run buildozer inside WSL2
4. Output APK to `android_port/bin/`

---

## Option 3: Direct Linux/WSL2 Build

If you prefer manual control or are already on Linux:

```bash
# Install dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y python3 cython3 build-essential openjdk-11-jdk android-sdk

# Setup Android SDK (if needed)
# See: https://buildozer.readthedocs.io/en/latest/installation.html

# Build APK
bash build_apk.sh
```

---

## Testing the APK

### On Android Device

```bash
# Enable USB Debugging on the device
# Then:
adb connect <device_ip>:5555
adb install android_port/bin/schoolbell-1.0-debug.apk
```

### On Emulator

```bash
# Start Android emulator
emulator -avd <avd_name> &

# Wait for it to boot, then install
adb install android_port/bin/schoolbell-1.0-debug.apk

# Launch app
adb shell am start -n org.example.schoolbell/.MainActivity
```

---

## Troubleshooting

### Build fails with "ANDROID_HOME not set"
Export the Android SDK path:
```bash
export ANDROID_HOME=/path/to/android-sdk
```

### "buildozer: command not found"
Install it:
```bash
pip install buildozer
```

### APK won't install: "Error installing package"
- Ensure device/emulator has sufficient storage
- Try signing the APK (for production release):
  ```bash
  jarsigner -verbose -sigalg SHA1withRSA -digestalg SHA1 \
    -keystore my-release-key.jks \
    android_port/bin/schoolbell-1.0-debug.apk alias_name
  ```

---

## Next Steps

1. **Test on device** to verify recordings and playback work
2. **Release build** (for Play Store):
   ```bash
   buildozer android release
   ```
3. **Sign & upload** to Google Play Store

Enjoy!
