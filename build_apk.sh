#!/bin/bash
# Build script for Android APK using Buildozer
# Run this on Linux or WSL2

set -e

echo "SchoolBell APK Build Script"
echo "============================"

# Check if buildozer is installed
if ! command -v buildozer &> /dev/null; then
    echo "Installing buildozer..."
    pip install buildozer cython
fi

# Check if ANDROID_HOME is set
if [ -z "$ANDROID_HOME" ]; then
    echo "ERROR: ANDROID_HOME not set. Please install Android SDK/NDK first."
    echo "Instructions: https://buildozer.readthedocs.io/en/latest/installation.html"
    exit 1
fi

echo "Building APK..."
cd android_port

# Clean previous builds
rm -rf .buildozer build

# Run buildozer
buildozer -v android debug

echo ""
echo "Build complete!"
echo "APK location: android_port/bin/schoolbell-1.0-debug.apk"
echo ""
echo "To test on device:"
echo "  adb connect <device_ip>:5555"
echo "  adb install bin/schoolbell-1.0-debug.apk"
echo ""
echo "Or use the emulator."
