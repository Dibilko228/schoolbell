[app]
title = SchoolBell
package.name = schoolbell
package.domain = org.example.schoolbell
source.dir = .
source.include_exts = py,png,jpg,kv,json
version = 1.0

requirements = python3,kivy==2.1.0,kivymd==0.104.2,plyer,pyjnius

orientation = landscape
fullscreen = 1

# Permissions
android.permissions = RECORD_AUDIO,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,INTERNET
android.api = 21
android.minapi = 21
android.ndk = 25b
android.arch = arm64-v8a

# Services/receivers (optional for background audio)
# android.services = org.example.schoolbell.AudioService

# Java classpaths for MediaRecorder/MediaPlayer
android.add_src = pyjnius_jni