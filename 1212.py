import os
import sys
import json
import time
import threading
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime, timedelta

import requests
import customtkinter as ctk
from tkinter import filedialog, messagebox, simpledialog
import tkinter as tk
from PIL import Image, ImageOps, ImageDraw, ImageFilter
import pygame
import sounddevice as sd
import numpy as np
from scipy.io import wavfile


APP_NAME = "SchoolBell"
CONFIG_NAME = "config.json"


DEFAULTS = {
    "photo_path": "",

    "lesson_start_sound_path": "",
    "lesson_end_sound_path": "",
    "siren_sound_path": "",
    "minute_of_silence_sound_path": "",

    "ALERTS_TOKEN": "",
    "ALERT_UID": 0,

    "minute_of_silence_enabled": True,
    "candle_gif_path": "",

    "silent_mode": False,

    "test_mode_on": False,
    "test_offset_seconds": 0,

    "entry_lock_enabled": False,
    "entry_password": "",

    "shutdown_enabled": False,
    "shutdown_time": "00:00",
}


DEFAULT_SCHEDULE_12 = [
    {"n": 1,  "start": "08:00", "end": "08:40"},
    {"n": 2,  "start": "08:45", "end": "09:25"},
    {"n": 3,  "start": "09:35", "end": "10:15"},
    {"n": 4,  "start": "10:20", "end": "11:00"},
    {"n": 5,  "start": "11:10", "end": "11:50"},
    {"n": 6,  "start": "12:00", "end": "12:40"},
    {"n": 7,  "start": "12:45", "end": "13:25"},
    {"n": 8,  "start": "13:35", "end": "14:15"},
    {"n": 9,  "start": "14:25", "end": "15:05"},
    {"n": 10, "start": "15:10", "end": "15:50"},
    {"n": 11, "start": "15:55", "end": "16:35"},
    {"n": 12, "start": "16:40", "end": "17:20"},
]


def app_dir() -> Path:
    p = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else Path.cwd()
    return p.parent if p.suffix else Path.cwd()


def now_local():
    return datetime.now()


def safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def is_hhmm(s: str) -> bool:
    try:
        hh, mm = s.split(":")
        hh = int(hh)
        mm = int(mm)
        return 0 <= hh <= 23 and 0 <= mm <= 59
    except Exception:
        return False


def hhmm_to_seconds(s: str) -> int:
    hh, mm = s.split(":")
    return int(hh) * 3600 + int(mm) * 60


def seconds_to_hhmmss(total: int) -> str:
    total = max(0, int(total))
    mm = total // 60
    ss = total % 60
    return f"{mm:02d}:{ss:02d}"


class SchoolBellApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        pygame.mixer.init()
        self._siren_channel = pygame.mixer.Channel(1)

        self.base_dir = app_dir()
        self.config_path = self.base_dir / CONFIG_NAME

        self.title("Шкільний дзвінок")
        self.geometry("1200x700")
        self.minsize(980, 620)

        self.fullscreen = True
        self.overrideredirect(True)
        self._go_fullscreen_geometry()

        self.right_mode = "photo"
        self.settings_open = False
        self.settings_tab = "main"

        self._alarm_overlay_on = False
        self._alarm_priority = False

        self._time_offset = timedelta(0)
        self.test_mode_on = False

        self.photo_path = ""
        self.photo_img_original = None
        self._photo_cache_key = None
        self._photo_cache_img = None
        self._photo_render_job = None

        self.candle_gif_path = ""
        self._gif_frames = []
        self._gif_index = 0
        self._gif_job = None

        self.minute_of_silence_enabled = True
        self.minute_of_silence_sound_path = ""
        self._mos_last_date = None
        self._mos_active = False
        self._mos_end_time = None

        self.lesson_start_sound_path = ""
        self.lesson_end_sound_path = ""
        self.siren_sound_path = ""
        self._siren_sound = None

        self.ALERTS_TOKEN = ""
        self.ALERT_UID = 0

        self.silent_mode = False

        self.entry_lock_enabled = False
        self.entry_password = ""

        self.shutdown_enabled = False
        self.shutdown_time = "00:00"
        self._shutdown_last_date = None

        self.schedule = [dict(x) for x in DEFAULT_SCHEDULE_12]
        self.lesson_rows = []

        self._load_config()

        if self.entry_lock_enabled:
            if not self.entry_password:
                messagebox.showerror("Помилка", "Увімкнено блокування входу, але пароль не задано.")
            else:
                if not self._ask_entry_password():
                    self.destroy()
                    return

        self._worker_stop = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)

        # КЛЮЧОВЕ ВИПРАВЛЕННЯ: антидубль дзвінків
        self._bell_fired_keys = set()
        self._bell_fired_date = None

        self._build_ui()

        self._update_clock()
        self.after(1500, self._poll_air_alert)

        self._worker_thread.start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _resolve_path(self, path: str) -> str:
        if not path:
            return ""
        try:
            if os.path.isabs(path):
                return path
            return str((self.base_dir / path).resolve())
        except Exception:
            return path

    def _basename(self, path: str) -> str:
        try:
            return os.path.basename(path) if path else ""
        except Exception:
            return ""

    def _go_fullscreen_geometry(self):
        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+0+0")

    def _ask_entry_password(self) -> bool:
        for _ in range(3):
            pw = simpledialog.askstring("Пароль", "Введи пароль для входу", show="*")
            if pw is None:
                return False
            if pw.strip() == self.entry_password:
                return True
            messagebox.showerror("Помилка", "Невірний пароль.")
        return False

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.topbar = ctk.CTkFrame(self, corner_radius=0, height=44)
        self.topbar.grid(row=0, column=0, sticky="ew")
        self.topbar.grid_columnconfigure(0, weight=1)

        self.settings_btn = ctk.CTkButton(self.topbar, text="⚙", width=46, height=30, command=self._toggle_settings_panel)
        self.settings_btn.grid(row=0, column=0, padx=(10, 0), pady=7, sticky="w")

        right = ctk.CTkFrame(self.topbar, corner_radius=0)
        right.grid(row=0, column=1, padx=10, pady=7, sticky="e")

        ctk.CTkButton(right, text="—", width=46, height=30, command=self._minimize).pack(side="left", padx=4)
        ctk.CTkButton(right, text="▢", width=46, height=30, command=self._toggle_fullscreen).pack(side="left", padx=4)
        ctk.CTkButton(right, text="✕", width=46, height=30, fg_color="#8b2b2b", hover_color="#a43737", command=self.on_close).pack(side="left", padx=4)

        self.btn_pick_siren = ctk.CTkButton(p, text="", command=self._pick_siren_sound)
        self.btn_pick_siren.grid(row=4, column=0, padx=12, pady=(0, 10), sticky="ew")
        img = img.convert("RGBA")
        base = Image.new("RGBA", (out_size, out_size), (0, 0, 0, 0))

        scale = 0.74
        inner = int(out_size * scale)
        logo = ImageOps.contain(img, (inner, inner), method=Image.Resampling.LANCZOS)

        cx = out_size / 2.0
        cy = out_size / 2.0
        x = int(cx - logo.width / 2.0)
        y = int(cy - logo.height / 2.0)

        glow = Image.new("RGBA", (out_size, out_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)

        r_outer = int(out_size * 0.49)
        r_inner = int(out_size * 0.42)

        draw.ellipse((cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer), fill=(60, 200, 255, 70))
        draw.ellipse((cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner), fill=(0, 0, 0, 0))
        glow = glow.filter(ImageFilter.GaussianBlur(18))

        ring = Image.new("RGBA", (out_size, out_size), (0, 0, 0, 0))
        d2 = ImageDraw.Draw(ring)
        d2.ellipse((cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer), outline=(90, 220, 255, 230), width=10)
        d2.ellipse((cx - r_outer + 10, cy - r_outer + 10, cx + r_outer - 10, cy + r_outer - 10), outline=(10, 110, 180, 160), width=2)

        base.alpha_composite(glow)
        base.alpha_composite(ring)
        base.alpha_composite(logo, (x, y))
        return base
    except Exception as e:
        print(f"Error creating neon ring logo: {e}")
        return Image.new("RGBA", (out_size, out_size), (0, 0, 0, 0))


def make_blue_bg(w: int, h: int) -> Image.Image:
    """Створює синій фон з градієнтом"""
    try:
        w = max(320, int(w))
        h = max(320, int(h))
        img = Image.new("RGB", (w, h), (6, 12, 22))
        g = Image.new("L", (1, h))
        for y in range(h):
            v = int(30 + 120 * (y / max(1, h - 1)))
            g.putpixel((0, y), v)
        grad = g.resize((w, h))
        blue = Image.new("RGB", (w, h), (10, 90, 170))
        img = Image.composite(blue, img, grad)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        d.rectangle((0, int(h * 0.40), w, int(h * 0.42)), fill=(90, 220, 255, 70))
        d.rectangle((0, int(h * 0.40) + 2, w, int(h * 0.40) + 4), fill=(90, 220, 255, 120))
        overlay = overlay.filter(ImageFilter.GaussianBlur(2))
        result = Image.alpha_composite(img.convert("RGBA"), overlay)
        return result.convert("RGBA")
    except Exception as e:
        print(f"Error creating blue background: {e}")
        return Image.new("RGBA", (max(320, int(w)), max(320, int(h))), (10, 20, 40, 255))


class SchoolBellApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        pygame.mixer.init()
        self._siren_channel = pygame.mixer.Channel(1)

        self.base_dir = app_dir()
        self.config_path = self.base_dir / CONFIG_NAME

        self.title("Шкільний дзвінок")
        self.geometry("1200x700")
        self.minsize(980, 620)

        self.fullscreen = True
        self.overrideredirect(True)
        self._go_fullscreen_geometry()

        self.right_mode = "photo"
        self.settings_open = False
        self.settings_tab = "main"

        self._alarm_overlay_on = False
        self._alarm_priority = False

        self._time_offset = timedelta(0)
        self.test_mode_on = False

        self.photo_path = ""
        self.photo_img_original = None
        self._photo_cache_key = None
        self._photo_cache_img = None
        self._photo_render_job = None

        self.candle_gif_path = ""
        self._gif_frames = []
        self._gif_index = 0
        self._gif_job = None

        self.minute_of_silence_enabled = True
        self.minute_of_silence_sound_path = ""
        self._mos_last_date = None
        self._mos_active = False
        self._mos_end_time = None

        self.lesson_start_sound_path = ""
        self.lesson_end_sound_path = ""
        self.siren_sound_path = ""
        self._siren_sound = None

        self.ALERTS_TOKEN = ""
        self.ALERT_UID = 0

        self.silent_mode = False

        self.entry_lock_enabled = False
        self.entry_password = ""

        self.shutdown_enabled = False
        self.shutdown_time = "00:00"
        
        # Для записів звуків
        self.custom_recordings = {}
        self.is_recording = False
        self.record_data = None
        self.record_start_time = None
        
        self.hibernation_enabled = False
        self.hibernation_time = "00:00"
        
        self.autostart_enabled = False
        self._shutdown_last_date = None

        self.schedule = [dict(x) for x in DEFAULT_SCHEDULE_12]
        self.lesson_rows = []

        self._load_config()

        if self.entry_lock_enabled:
            if not self.entry_password:
                messagebox.showerror("Помилка", "Увімкнено блокування входу, але пароль не задано.")
            else:
                if not self._ask_entry_password():
                    self.destroy()
                    return

        self._worker_stop = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)

        # КЛЮЧОВЕ ВИПРАВЛЕННЯ: антидубль дзвінків
        self._bell_fired_keys = set()
        self._bell_fired_date = None

        self._build_ui()

        # Background image for entire window (keeps photo image untouched)
        self._bg_cache_key = None
        self._bg_cache_img = None
        self._bg_render_job = None
        self._bg_label = ctk.CTkLabel(self, text="")
        self._bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            self._bg_label.lower()
        except Exception:
            pass
        self.bind("<Configure>", lambda e: self._schedule_bg_render())
        self._schedule_bg_render()
        self._update_clock()
        self.after(1500, self._poll_air_alert)

        self._worker_thread.start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _resolve_path(self, path: str) -> str:
        if not path:
            return ""
        try:
            if os.path.isabs(path):
                return path
            return str((self.base_dir / path).resolve())
        except Exception:
            return path

    def _basename(self, path: str) -> str:
        try:
            return os.path.basename(path) if path else ""
        except Exception:
            return ""

    def _go_fullscreen_geometry(self):
        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+0+0")

    def _ask_entry_password(self) -> bool:
        for _ in range(3):
            pw = simpledialog.askstring("Пароль", "Введи пароль для входу", show="*")
            if pw is None:
                return False
            if pw.strip() == self.entry_password:
                return True
            messagebox.showerror("Помилка", "Невірний пароль.")
        return False

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.topbar = ctk.CTkFrame(self, corner_radius=0, height=44)
        self.topbar.grid(row=0, column=0, sticky="ew")
        self.topbar.grid_columnconfigure(0, weight=1)

        self.settings_btn = ctk.CTkButton(self.topbar, text="⚙", width=46, height=30, command=self._toggle_settings_panel)
        self.settings_btn.grid(row=0, column=0, padx=(10, 0), pady=7, sticky="w")

        right = ctk.CTkFrame(self.topbar, corner_radius=0)
        right.grid(row=0, column=1, padx=10, pady=7, sticky="e")

        ctk.CTkButton(right, text="—", width=46, height=30, command=self._minimize).pack(side="left", padx=4)
        ctk.CTkButton(right, text="▢", width=46, height=30, command=self._toggle_fullscreen).pack(side="left", padx=4)
        ctk.CTkButton(right, text="✕", width=46, height=30, fg_color="#8b2b2b", hover_color="#a43737", command=self.on_close).pack(side="left", padx=4)

        self.body = ctk.CTkFrame(self, corner_radius=0)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1, uniform="HALF")
        self.body.grid_columnconfigure(1, weight=1, uniform="HALF")

        self.left = ctk.CTkFrame(self.body, corner_radius=18)
        self.left.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        self.left.grid_columnconfigure(0, weight=1)
        self.left.grid_rowconfigure(0, weight=1, uniform="L2")
        self.left.grid_rowconfigure(1, weight=1, uniform="L2")

        self.clock_card = ctk.CTkFrame(self.left, corner_radius=18)
        self.clock_card.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

        self.time_label = ctk.CTkLabel(self.clock_card, text="", font=ctk.CTkFont(size=170, weight="bold"))
        self.time_label.place(relx=0.5, rely=0.48, anchor="center")

        self.date_label = ctk.CTkLabel(self.clock_card, text="", font=ctk.CTkFont(size=85))
        self.date_label.place(relx=0.5, rely=0.74, anchor="center")

        self.lesson_card = ctk.CTkFrame(self.left, corner_radius=18)
        self.lesson_card.grid(row=1, column=0, sticky="nsew", padx=14, pady=14)
        self.lesson_card.grid_rowconfigure(0, weight=1)
        self.lesson_card.grid_rowconfigure(1, weight=0)
        self.lesson_card.grid_columnconfigure(0, weight=1)

        self.lesson_now_label = ctk.CTkLabel(
            self.lesson_card,
            text="",
            font=ctk.CTkFont(size=170, weight="bold"),
            justify="center",
        )
        self.lesson_now_label.grid(row=0, column=0, sticky="nsew", padx=18, pady=(18, 6))

        self.progress = ctk.CTkProgressBar(self.lesson_card)
        self.progress.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        self.progress.set(0)

        self.right = ctk.CTkFrame(self.body, corner_radius=18)
        self.right.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)
        self.right.grid_rowconfigure(0, weight=1)
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_propagate(False)

        self.photo_view = ctk.CTkFrame(self.right, corner_radius=18)
        self.photo_view.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        self.photo_view.grid_rowconfigure(0, weight=1)
        self.photo_view.grid_columnconfigure(0, weight=1)
        self.photo_view.grid_propagate(False)

        self.photo_label = ctk.CTkLabel(self.photo_view, text="Фото не вибране")
        self.photo_label.grid(row=0, column=0, sticky="nsew")
        self.photo_label.grid_propagate(False)

        self.photo_view.bind("<Configure>", lambda e: self._schedule_photo_render())

        self.settings_view = ctk.CTkFrame(self.right, corner_radius=18)
        self.settings_view.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        self.settings_view.grid_remove()
        self.settings_view.grid_columnconfigure(0, weight=1)
        self.settings_view.grid_rowconfigure(40, weight=1)

        header = ctk.CTkLabel(self.settings_view, text="Налаштування", font=ctk.CTkFont(size=22, weight="bold"))
        header.grid(row=0, column=0, padx=18, pady=(18, 10), sticky="w")

        tabs = ctk.CTkFrame(self.settings_view, corner_radius=18)
        tabs.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")
        tabs.grid_columnconfigure(0, weight=1)
        tabs.grid_columnconfigure(1, weight=1)
        tabs.grid_columnconfigure(2, weight=1)

        self.btn_tab_main = ctk.CTkButton(tabs, text="Основне", command=lambda: self._set_settings_tab("main"))
        self.btn_tab_main.grid(row=0, column=0, padx=(0, 4), pady=10, sticky="ew")

        self.btn_tab_extra = ctk.CTkButton(tabs, text="Додатково", command=lambda: self._set_settings_tab("extra"))
        self.btn_tab_extra.grid(row=0, column=1, padx=(4, 4), pady=10, sticky="ew")
        
        self.btn_tab_recordings = ctk.CTkButton(tabs, text="🎙 Записи", command=lambda: self._set_settings_tab("recordings"))
        self.btn_tab_recordings.grid(row=0, column=2, padx=(4, 0), pady=10, sticky="ew")

        self.btn_tab_main = ctk.CTkButton(tabs, text="Основне", command=lambda: self._set_settings_tab("main"))
        self.btn_tab_main.grid(row=0, column=0, padx=(0, 8), pady=10, sticky="ew")

        self.btn_tab_extra = ctk.CTkButton(tabs, text="Додатково", command=lambda: self._set_settings_tab("extra"))
        self.btn_tab_extra.grid(row=0, column=1, padx=(8, 0), pady=10, sticky="ew")

        self.panel_main = ctk.CTkFrame(self.settings_view, corner_radius=18)
        self.panel_main.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.panel_main.grid_columnconfigure(0, weight=1)
        self.panel_main.grid_rowconfigure(30, weight=1)

        self.panel_extra = ctk.CTkFrame(self.settings_view, corner_radius=18)
        self.panel_extra.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.panel_extra.grid_remove()
        self.panel_extra.grid_columnconfigure(0, weight=1)
        self.panel_extra.grid_rowconfigure(30, weight=1)
        
        self.panel_recordings = ctk.CTkFrame(self.settings_view, corner_radius=18)
        self.panel_recordings.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.panel_recordings.grid_remove()
        self.panel_recordings.grid_columnconfigure(0, weight=1)
        self.panel_recordings.grid_rowconfigure(40, weight=1)

        self._build_main_panel()
        self._build_extra_panel()
        self._build_recordings_panel()
        self._set_settings_tab(self.settings_tab)

        self._build_main_panel()
        self._build_extra_panel()
        self._set_settings_tab(self.settings_tab)

        self.candle_view = ctk.CTkFrame(self.right, corner_radius=18)
        self.candle_view.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        self.candle_view.grid_remove()
        self.candle_view.grid_rowconfigure(1, weight=1)
        self.candle_view.grid_columnconfigure(0, weight=1)

        self.candle_title = ctk.CTkLabel(
            self.candle_view,
            text="Хвилина мовчання",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        self.candle_title.grid(row=0, column=0, padx=18, pady=(18, 10), sticky="n")

        self.video_label = ctk.CTkLabel(self.candle_view, text="")
        self.video_label.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")

        self.alarm_overlay = ctk.CTkFrame(self, corner_radius=0, fg_color="#B00020")
        self.alarm_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.alarm_overlay.lift()
        self.alarm_overlay.place_forget()

        self.alarm_label = ctk.CTkLabel(self.alarm_overlay, text="ТРИВОГА", font=ctk.CTkFont(size=120, weight="bold"), text_color="white")
        self.alarm_label.place(relx=0.5, rely=0.42, anchor="center")

        self.alarm_hint = ctk.CTkLabel(self.alarm_overlay, text="Перейдіть в укриття", font=ctk.CTkFont(size=40, weight="bold"), text_color="white")
        self.alarm_hint.place(relx=0.5, rely=0.58, anchor="center")

        self.alarm_btn = ctk.CTkButton(self.alarm_overlay, text="Сховати", width=220, height=48, command=self._hide_alarm_overlay)
        self.alarm_btn.place(relx=0.5, rely=0.73, anchor="center")

        self.alarm_map_btn = ctk.CTkButton(self.alarm_overlay, text="Відкрити мапу тривог", width=260, height=48, command=lambda: webbrowser.open("https://alerts.in.ua/mini"))
        self.alarm_map_btn.place(relx=0.5, rely=0.82, anchor="center")

        self._show_right("photo")
        self._schedule_photo_render()

    def _build_main_panel(self):
        p = self.panel_main

        top_btns = ctk.CTkFrame(p, corner_radius=18)
        top_btns.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 10))
        top_btns.grid_columnconfigure(0, weight=1)
        top_btns.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(top_btns, text="Розклад", command=self._toggle_schedule_box).grid(row=0, column=0, padx=(0, 8), pady=10, sticky="ew")
        ctk.CTkButton(top_btns, text="Фото", command=self._pick_photo).grid(row=0, column=1, padx=(8, 0), pady=10, sticky="ew")

        self.btn_pick_start = ctk.CTkButton(p, text="", command=self._pick_lesson_start_sound)
        self.btn_pick_start.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")

        self.btn_pick_end = ctk.CTkButton(p, text="", command=self._pick_lesson_end_sound)
        self.btn_pick_end.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="ew")

        test_row = ctk.CTkFrame(p, corner_radius=18)
        test_row.grid(row=3, column=0, padx=12, pady=(0, 10), sticky="ew")
        test_row.grid_columnconfigure(0, weight=1)
        test_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(test_row, text="Тест урок", command=lambda: self._play_sound(self.lesson_start_sound_path)).grid(row=0, column=0, padx=(0, 8), pady=10, sticky="ew")
        ctk.CTkButton(test_row, text="Тест кінець", command=lambda: self._play_sound(self.lesson_end_sound_path)).grid(row=0, column=1, padx=(8, 0), pady=10, sticky="ew")

        self.btn_pick_siren = ctk.CTkButton(p, text="", command=self._pick_siren_sound)
        self.btn_pick_siren.grid(row=4, column=0, padx=12, pady=(0, 10), sticky="ew")

        token_box = ctk.CTkFrame(p, corner_radius=18)
        token_box.grid(row=5, column=0, padx=12, pady=(0, 10), sticky="ew")
        token_box.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(token_box, text="Token").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.token_var = ctk.StringVar(value=self.ALERTS_TOKEN)
        ctk.CTkEntry(token_box, textvariable=self.token_var).grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(token_box, text="UID").grid(row=1, column=0, padx=10, pady=(0, 10), sticky="w")
        self.uid_var = ctk.StringVar(value=str(self.ALERT_UID))
        ctk.CTkEntry(token_box, textvariable=self.uid_var).grid(row=1, column=1, padx=10, pady=(0, 10), sticky="ew")

        ctk.CTkButton(p, text="Зберегти", command=self._save_config).grid(row=6, column=0, padx=12, pady=(0, 12), sticky="ew")

        self.schedule_box = ctk.CTkFrame(p, corner_radius=18)
        self.schedule_box.grid(row=30, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.schedule_box.grid_columnconfigure(0, weight=1)
        self.schedule_box.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self.schedule_box, corner_radius=18)
        header.grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Розклад на всі дні (12 уроків)").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkButton(header, text="Застосувати", command=self._apply_editor_to_schedule).grid(row=0, column=1, padx=10, pady=10, sticky="e")

        ctk.CTkLabel(self.schedule_box, text="Урок     Початок     Кінець     Запис(початок)     Запис(кінець)").grid(row=1, column=0, padx=12, pady=(0, 6), sticky="w")

        self.schedule_list = ctk.CTkScrollableFrame(self.schedule_box, corner_radius=18)
        self.schedule_list.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self._build_schedule_rows(self.schedule_list)
        self._apply_schedule_to_editor()

        self.schedule_box.grid_remove()

        self._refresh_sound_button_titles()

    def _build_extra_panel(self):
        p = self.panel_extra

        row1 = ctk.CTkFrame(p, corner_radius=18)
        row1.grid(row=0, column=0, padx=12, pady=(12, 10), sticky="ew")
        row1.grid_columnconfigure(0, weight=1)

        self.silent_var = ctk.BooleanVar(value=self.silent_mode)
        ctk.CTkCheckBox(row1, text="Тихий режим", variable=self.silent_var, command=self._apply_silent).grid(row=0, column=0, padx=10, pady=10, sticky="w")

        row2 = ctk.CTkFrame(p, corner_radius=18)
        row2.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")
        row2.grid_columnconfigure(0, weight=1)

        self.mos_var = ctk.BooleanVar(value=self.minute_of_silence_enabled)
        ctk.CTkCheckBox(row2, text="Хвилина мовчання 09:00", variable=self.mos_var, command=self._apply_mos).grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.btn_pick_mos = ctk.CTkButton(row2, text="", command=self._pick_mos_sound)
        self.btn_pick_mos.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        self.btn_pick_gif = ctk.CTkButton(row2, text="Обрати гіфку", command=self._pick_candle_gif)
        self.btn_pick_gif.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")

        row3 = ctk.CTkFrame(p, corner_radius=18)
        row3.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="ew")
        row3.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row3, text="Тест час (HH:MM)").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.test_time_var = ctk.StringVar(value="")
        ctk.CTkEntry(row3, textvariable=self.test_time_var, justify="center", width=140).grid(row=0, column=1, padx=10, pady=10, sticky="w")

        buttons = ctk.CTkFrame(row3, corner_radius=18)
        buttons.grid(row=0, column=2, padx=10, pady=10, sticky="e")
        ctk.CTkButton(buttons, text="Увімкнути", width=110, command=self._enable_test_time).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="Вимкнути", width=110, command=self._disable_test_time).pack(side="left", padx=6)

        row4 = ctk.CTkFrame(p, corner_radius=18)
        row4.grid(row=3, column=0, padx=12, pady=(0, 10), sticky="ew")
        row4.grid_columnconfigure(0, weight=1)
        row4.grid_columnconfigure(1, weight=1)

        self.entry_lock_var = ctk.BooleanVar(value=self.entry_lock_enabled)
        ctk.CTkCheckBox(row4, text="Блокування входу", variable=self.entry_lock_var, command=self._apply_entry_lock).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkButton(row4, text="Задати пароль", command=self._set_entry_password).grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        row5 = ctk.CTkFrame(p, corner_radius=18)
        row5.grid(row=4, column=0, padx=12, pady=(0, 12), sticky="ew")
        row5.grid_columnconfigure(0, weight=1)

        self.shutdown_var = ctk.BooleanVar(value=self.shutdown_enabled)
        ctk.CTkCheckBox(row5, text="Вимикати ПК щодня у час", variable=self.shutdown_var, command=self._apply_shutdown_enabled).grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )
        self.btn_set_shutdown = ctk.CTkButton(row5, text=f"Час вимкнення: {self.shutdown_time}", command=self._set_shutdown_time)
        self.btn_set_shutdown.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        row6 = ctk.CTkFrame(p, corner_radius=18)
        row6.grid(row=5, column=0, padx=12, pady=(0, 12), sticky="ew")
        row6.grid_columnconfigure(0, weight=1)

        self.hibernation_var = ctk.BooleanVar(value=self.hibernation_enabled)
        ctk.CTkCheckBox(row6, text="Гібернація ПК щодня у час", variable=self.hibernation_var, command=self._apply_hibernation_enabled).grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )
        self.btn_set_hibernation = ctk.CTkButton(row6, text=f"Час гібернації: {self.hibernation_time}", command=self._set_hibernation_time)
        self.btn_set_hibernation.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        row7 = ctk.CTkFrame(p, corner_radius=18)
        row7.grid(row=6, column=0, padx=12, pady=(0, 12), sticky="ew")
        row7.grid_columnconfigure(0, weight=1)

        self.autostart_var = ctk.BooleanVar(value=self.autostart_enabled)
        ctk.CTkCheckBox(row7, text="Автозагрузка з Windows", variable=self.autostart_var, command=self._apply_autostart).grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )

        self._refresh_sound_button_titles()

    def _set_settings_tab(self, tab: str):
        self.settings_tab = tab
        self.panel_main.grid_remove()
        self.panel_extra.grid_remove()
        self.panel_recordings.grid_remove()
        
        if tab == "main":
            self.panel_main.grid()
        elif tab == "extra":
            self.panel_extra.grid()
        elif tab == "recordings":
            self.panel_recordings.grid()
            self._refresh_recordings_list()
        
        self._save_config()

    def _show_right(self, mode: str):
        if self.right_mode == "candle" and mode != "candle":
            self._stop_candle_gif()

        self.right_mode = mode
        self.photo_view.grid_remove()
        self.settings_view.grid_remove()
        self.candle_view.grid_remove()

        if mode == "photo":
            self.photo_view.grid()
            self._schedule_photo_render()
        elif mode == "settings":
            self.settings_view.grid()
        else:
            self.candle_view.grid()
            self._start_candle_gif()

    def _toggle_settings_panel(self):
        self.settings_open = not self.settings_open
        if self.settings_open:
            self._show_right("settings")
        else:
            self._show_right("photo")

    def _toggle_schedule_box(self):
        if self.schedule_box.winfo_ismapped():
            self.schedule_box.grid_remove()
        else:
            self.schedule_box.grid()

    def _minimize(self):
        self.overrideredirect(False)
        self.update_idletasks()
        self.iconify()
        self.bind("<Map>", self._on_restore)

    def _on_restore(self, event=None):
        self.unbind("<Map>")
        self.after(60, lambda: self.overrideredirect(True))

    def _toggle_fullscreen(self):
        if self.fullscreen:
            self.fullscreen = False
            self.overrideredirect(False)
            self.geometry("1200x700+50+50")
        else:
            self.fullscreen = True
            self.overrideredirect(True)
            self._go_fullscreen_geometry()

    def _pick_photo(self):
        path = filedialog.askopenfilename(
            title="Обери фото",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")]
        )
        if not path:
            return

        self.photo_path = path
        try:
            self.photo_img_original = Image.open(self.photo_path).convert("RGBA")
        except Exception as e:
            self.photo_img_original = None
            messagebox.showerror("Помилка", f"Не вдалося завантажити фото:\n{e}")
            return

        self._photo_cache_key = None
        self._photo_cache_img = None
        self._schedule_photo_render()
        self._save_config()

    def _schedule_photo_render(self):
        if self._photo_render_job:
            try:
                self.after_cancel(self._photo_render_job)
            except Exception:
                pass
        self._photo_render_job = self.after(60, self._render_photo_fit)

    def _render_photo_fit(self):
        self._photo_render_job = None
        if self.right_mode != "photo":
            return

        if not self.photo_img_original:
            self.photo_label.configure(text="Фото не вибране", image=None)
            return

        self.update_idletasks()
        w = self.photo_view.winfo_width()
        h = self.photo_view.winfo_height()
        if w < 100 or h < 100:
            return

        key = (w, h, id(self.photo_img_original))
        if self._photo_cache_key == key and self._photo_cache_img is not None:
            self.photo_label.configure(image=self._photo_cache_img, text="")
            self.photo_label.image = self._photo_cache_img
            return

        try:
            # Resize image to fit without any effects
            photo = ImageOps.contain(self.photo_img_original, (w, h), method=Image.Resampling.LANCZOS)
            cimg = ctk.CTkImage(light_image=photo, dark_image=photo, size=(photo.width, photo.height))
            self._photo_cache_key = key
            self._photo_cache_img = cimg

            self.photo_label.configure(image=cimg, text="")
            self.photo_label.image = cimg
        except Exception as e:
            self.photo_label.configure(text=f"Помилка фото:\n{e}", image=None)

    def _schedule_bg_render(self):
        if self._bg_render_job:
            try:
                self.after_cancel(self._bg_render_job)
            except Exception:
                pass
        self._bg_render_job = self.after(80, self._render_bg)

    def _render_bg(self):
        self._bg_render_job = None
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 100 or h < 100:
            return

        key = (w, h)
        if self._bg_cache_key == key and self._bg_cache_img is not None:
            try:
                self._bg_label.configure(image=self._bg_cache_img)
                self._bg_label.image = self._bg_cache_img
            except Exception:
                pass
            return

        try:
            bg = make_blue_bg(w, h)
            cimg = ctk.CTkImage(light_image=bg, dark_image=bg, size=(w, h))
            self._bg_cache_key = key
            self._bg_cache_img = cimg
            self._bg_label.configure(image=cimg)
            self._bg_label.image = cimg
            try:
                self._bg_label.lower()
            except Exception:
                pass
        except Exception:
            pass

    def _refresh_sound_button_titles(self):
        s1 = self._basename(getattr(self, "lesson_start_sound_path", ""))
        s2 = self._basename(getattr(self, "lesson_end_sound_path", ""))
        ss = self._basename(getattr(self, "siren_sound_path", ""))
        sm = self._basename(getattr(self, "minute_of_silence_sound_path", ""))

        t1 = "Обрати звук на урок"
        t2 = "Обрати звук на кінець уроку"
        ts = "Обрати сирену"
        tm = "Обрати звук на хвилину мовчання"

        if s1:
            t1 = f"{t1}  {s1}"
        if s2:
            t2 = f"{t2}  {s2}"
        if ss:
            ts = f"{ts}  {ss}"
        if sm:
            tm = f"{tm}  {sm}"

        if hasattr(self, "btn_pick_start"):
            self.btn_pick_start.configure(text=t1)
        if hasattr(self, "btn_pick_end"):
            self.btn_pick_end.configure(text=t2)
        if hasattr(self, "btn_pick_siren"):
            self.btn_pick_siren.configure(text=ts)
        if hasattr(self, "btn_pick_mos"):
            self.btn_pick_mos.configure(text=tm)
        if hasattr(self, "btn_set_shutdown"):
            self.btn_set_shutdown.configure(text=f"Час вимкнення: {getattr(self, 'shutdown_time', '00:00')}")
        if hasattr(self, "btn_set_hibernation"):
            self.btn_set_hibernation.configure(text=f"Час гібернації: {getattr(self, 'hibernation_time', '00:00')}")

    def _pick_lesson_start_sound(self):
        path = filedialog.askopenfilename(title="Обери звук на урок", filetypes=[("Audio", "*.wav *.mp3 *.ogg"), ("All files", "*.*")])
        if path:
            self.lesson_start_sound_path = path
            self._refresh_sound_button_titles()
            self._save_config()

    def _pick_lesson_end_sound(self):
        path = filedialog.askopenfilename(title="Обери звук на кінець уроку", filetypes=[("Audio", "*.wav *.mp3 *.ogg"), ("All files", "*.*")])
        if path:
            self.lesson_end_sound_path = path
            self._refresh_sound_button_titles()
            self._save_config()

    def _pick_siren_sound(self):
        path = filedialog.askopenfilename(title="Обери звук сирени", filetypes=[("Audio", "*.wav *.mp3 *.ogg"), ("All files", "*.*")])
        if not path:
            return
        self.siren_sound_path = path
        p = self._resolve_path(self.siren_sound_path)
        try:
            self._siren_sound = pygame.mixer.Sound(p)
            self._siren_sound.set_volume(1.0)
            self._refresh_sound_button_titles()
            self._save_config()
        except Exception as e:
            self._siren_sound = None
            messagebox.showerror("Помилка", f"Не вдалося завантажити сирену:\n{e}")

    def _pick_mos_sound(self):
        path = filedialog.askopenfilename(title="Обери звук на хвилину мовчання", filetypes=[("Audio", "*.wav *.mp3 *.ogg"), ("All files", "*.*")])
        if path:
            self.minute_of_silence_sound_path = path
            self._refresh_sound_button_titles()
            self._save_config()

    def _stop_all_non_alarm_audio(self):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def _play_sound(self, path: str):
        if self._alarm_priority:
            return
        p = self._resolve_path(path)
        if not p or not os.path.exists(p):
            return
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.load(p)
            pygame.mixer.music.play()
        except Exception:
            pass

    def _start_siren(self):
        if not self._siren_sound:
            p = self._resolve_path(self.siren_sound_path)
            if p and os.path.exists(p):
                try:
                    self._siren_sound = pygame.mixer.Sound(p)
                    self._siren_sound.set_volume(1.0)
                except Exception:
                    self._siren_sound = None

        if self._siren_sound and not self._siren_channel.get_busy():
            try:
                self._siren_channel.play(self._siren_sound, loops=-1)
            except Exception:
                pass

    def _stop_siren(self):
        try:
            if self._siren_channel.get_busy():
                self._siren_channel.stop()
        except Exception:
            pass

    def _pick_candle_gif(self):
        path = filedialog.askopenfilename(title="Обери гіфку (gif)", filetypes=[("GIF", "*.gif"), ("All files", "*.*")])
        if not path:
            return
        self.candle_gif_path = path
        self._load_gif_frames()
        self._save_config()
        if self.right_mode == "candle":
            self._start_candle_gif()

    def _load_gif_frames(self):
        self._gif_frames = []
        self._gif_index = 0
        p = self._resolve_path(self.candle_gif_path)
        if not p or not os.path.exists(p):
            return
        try:
            import imageio
            reader = imageio.get_reader(p)
            for frame in reader:
                self._gif_frames.append(Image.fromarray(frame))
            try:
                reader.close()
            except Exception:
                pass
        except Exception:
            self._gif_frames = []

    def _start_candle_gif(self):
        self._stop_candle_gif()
        if not self._gif_frames:
            self.video_label.configure(text="Гіфка не вибрана або не читається", image=None)
            return
        self._gif_next_frame()

    def _gif_next_frame(self):
        if self.right_mode != "candle" or not self._gif_frames:
            return

        img = self._gif_frames[self._gif_index % len(self._gif_frames)]
        self._gif_index += 1

        w = max(320, self.video_label.winfo_width())
        h = max(320, self.video_label.winfo_height())
        img2 = ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

        cimg = ctk.CTkImage(light_image=img2, dark_image=img2, size=(w, h))
        self.video_label.configure(image=cimg, text="")
        self.video_label.image = cimg

        self._gif_job = self.after(80, self._gif_next_frame)

    def _stop_candle_gif(self):
        if self._gif_job:
            try:
                self.after_cancel(self._gif_job)
            except Exception:
                pass
            self._gif_job = None

    def _apply_silent(self):
        self.silent_mode = bool(self.silent_var.get())
        self._save_config()

    def _apply_mos(self):
        self.minute_of_silence_enabled = bool(self.mos_var.get())
        self._save_config()

    def _apply_entry_lock(self):
        self.entry_lock_enabled = bool(self.entry_lock_var.get())
        self._save_config()

    def _set_entry_password(self):
        pw = simpledialog.askstring("Пароль", "Введи пароль для входу", show="*")
        if pw is None:
            return
        pw = pw.strip()
        if len(pw) < 3:
            messagebox.showerror("Помилка", "Пароль має бути хоча б 3 символи.")
            return
        self.entry_password = pw
        self.entry_lock_enabled = True
        self.entry_lock_var.set(True)
        self._save_config()
        messagebox.showinfo("Ок", "Пароль встановлено.")

    def _apply_shutdown_enabled(self):
        self.shutdown_enabled = bool(self.shutdown_var.get())
        self._save_config()

    def _set_shutdown_time(self):
        s = simpledialog.askstring("Вимкнення ПК", "Введи час у форматі HH:MM", initialvalue=self.shutdown_time)
        if s is None:
            return
        s = s.strip()
        if not is_hhmm(s):
            messagebox.showerror("Помилка", "Введи час у форматі HH:MM, наприклад 18:30")
            return
        self.shutdown_time = s
        self._refresh_sound_button_titles()
        self._save_config()

    def _apply_hibernation_enabled(self):
        self.hibernation_enabled = bool(self.hibernation_var.get())
        self._save_config()

    def _set_hibernation_time(self):
        s = simpledialog.askstring("Гібернація ПК", "Введи час у форматі HH:MM", initialvalue=self.hibernation_time)
        if s is None:
            return
        s = s.strip()
        if not is_hhmm(s):
            messagebox.showerror("Помилка", "Введи час у форматі HH:MM, наприклад 18:30")
            return
        self.hibernation_time = s
        self._refresh_sound_button_titles()
        self._save_config()

    def _apply_autostart(self):
        self.autostart_enabled = bool(self.autostart_var.get())
        self._save_config()
        self._setup_autostart()

    def _setup_autostart(self):
        try:
            if self.autostart_enabled:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                program_path = os.path.abspath(sys.argv[0])
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, program_path)
                winreg.CloseKey(key)
                messagebox.showinfo("Ок", "Автозагрузка увімкнена.")
            else:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except Exception:
                    pass
                winreg.CloseKey(key)
                messagebox.showinfo("Ок", "Автозагрузка вимкнена.")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося налаштувати автозагрузку:\n{e}")

    def _build_schedule_rows(self, parent):
        for w in parent.winfo_children():
            w.destroy()
        self.lesson_rows.clear()

        for i in range(1, 13):
            start_var = ctk.StringVar(value="")
            end_var = ctk.StringVar(value="")
            start_rec_var = ctk.StringVar(value="")
            end_rec_var = ctk.StringVar(value="")

            row = ctk.CTkFrame(parent, corner_radius=14)
            row.grid(row=i, column=0, sticky="ew", padx=8, pady=6)
            row.grid_columnconfigure(0, minsize=80)
            row.grid_columnconfigure(1, weight=1)
            row.grid_columnconfigure(2, weight=1)
            row.grid_columnconfigure(3, weight=1)
            row.grid_columnconfigure(4, weight=1)

            ctk.CTkLabel(row, text=str(i), width=70, anchor="center").grid(row=0, column=0, padx=(10, 6), pady=12, sticky="ew")
            ctk.CTkEntry(row, textvariable=start_var, justify="center", font=ctk.CTkFont(size=16)).grid(row=0, column=1, padx=6, pady=12, sticky="ew")
            ctk.CTkEntry(row, textvariable=end_var, justify="center", font=ctk.CTkFont(size=16)).grid(row=0, column=2, padx=(6, 6), pady=12, sticky="ew")

            # Attach recording buttons for start/end
            # Buttons show current attached recording name or 'Прикріпити'
            attach_start_btn = ctk.CTkButton(row, text=(start_rec_var.get() or "Прикріпити"), width=160, command=lambda idx=i-1: self._attach_recording_dialog(idx, "start"))
            attach_start_btn.grid(row=0, column=3, padx=4, pady=12, sticky="ew")
            attach_end_btn = ctk.CTkButton(row, text=(end_rec_var.get() or "Прикріпити"), width=160, command=lambda idx=i-1: self._attach_recording_dialog(idx, "end"))
            attach_end_btn.grid(row=0, column=4, padx=(4, 10), pady=12, sticky="ew")

            # Keep buttons updated when var changes
            def _make_updater(btn, var):
                def _upd(*a, btn=btn, var=var):
                    val = var.get() or "Прикріпити"
                    try:
                        btn.configure(text=val)
                    except Exception:
                        pass
                return _upd

            start_rec_var.trace_add("write", _make_updater(attach_start_btn, start_rec_var))
            end_rec_var.trace_add("write", _make_updater(attach_end_btn, end_rec_var))

            self.lesson_rows.append((i, start_var, end_var, start_rec_var, end_rec_var))

    def _apply_schedule_to_editor(self):
        items = self.schedule
        for idx in range(12):
            n, sv, ev, srv, erv = self.lesson_rows[idx]
            item = items[idx] if idx < len(items) else None
            sv.set(item.get("start", "") if item else "")
            ev.set(item.get("end", "") if item else "")
            srv.set(item.get("recording_start", "") if item else "")
            erv.set(item.get("recording_end", "") if item else "")

    def _read_lessons_from_ui(self):
        result = []
        for entry in self.lesson_rows:
            # entry == (n, start_var, end_var [, start_rec_var, end_rec_var])
            n = entry[0]
            s = entry[1].get().strip()
            e = entry[2].get().strip()
            rec_start = entry[3].get().strip() if len(entry) > 3 else ""
            rec_end = entry[4].get().strip() if len(entry) > 4 else ""
            if not s and not e:
                continue
            if is_hhmm(s) and is_hhmm(e):
                item = {"n": n, "start": s, "end": e}
                if rec_start:
                    item["recording_start"] = rec_start
                if rec_end:
                    item["recording_end"] = rec_end
                result.append(item)
        result.sort(key=lambda x: x["n"])
        return result

    def _attach_recording_dialog(self, row_idx: int, when: str):
        """Open a small dialog to pick a recording for a schedule row.
        when: "start" or "end""" 
        names = list(self.custom_recordings.keys())
        top = ctk.CTkToplevel(self)
        top.title("Вибір запису")
        top.geometry("360x300")
        lbl = ctk.CTkLabel(top, text="Оберіть запис:")
        lbl.pack(padx=8, pady=8)

        listbox = tk.Listbox(top)
        for n in names:
            listbox.insert("end", n)
        listbox.pack(fill="both", expand=True, padx=8, pady=8)

        def on_ok():
            sel = listbox.curselection()
            val = names[sel[0]] if sel else ""
            if 0 <= row_idx < len(self.lesson_rows):
                entry = self.lesson_rows[row_idx]
                if when == "start" and len(entry) > 3:
                    entry[3].set(val)
                if when == "end" and len(entry) > 4:
                    entry[4].set(val)
            top.destroy()

        btns = ctk.CTkFrame(top)
        btns.pack(padx=8, pady=8)
        ctk.CTkButton(btns, text="OK", command=on_ok).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Відмінити", command=top.destroy).pack(side="left", padx=6)

    def _apply_editor_to_schedule(self):
        rows = self._read_lessons_from_ui()
        if not rows:
            messagebox.showerror("Помилка", "Розклад порожній.")
            return
        self.schedule = rows
        self._save_config()
        messagebox.showinfo("Ок", "Розклад збережено.")

    def _now_dt(self):
        return now_local() + (self._time_offset if self.test_mode_on else timedelta(0))

    def _update_clock(self):
        now = self._now_dt()
        self.time_label.configure(text=now.strftime("%H:%M:%S"))
        self.date_label.configure(text=now.strftime("%d.%m.%Y"))

        self._minute_of_silence_tick(now)
        self._update_lesson_or_break(now)

        self.after(250, self._update_clock)

    def _minute_of_silence_tick(self, now_dt: datetime):
        if self._alarm_priority:
            return

        if not self.minute_of_silence_enabled:
            self._mos_active = False
            self._mos_end_time = None
            if self.right_mode == "candle" and not self.settings_open:
                self._show_right("photo")
            return

        today = now_dt.date()

        if self._mos_active:
            if self._mos_end_time and now_dt >= self._mos_end_time:
                self._mos_active = False
                self._mos_end_time = None
                if self.right_mode == "candle" and not self.settings_open:
                    self._show_right("photo")
            return

        if self._mos_last_date == today:
            return

        if now_dt.hour == 9 and now_dt.minute == 0 and now_dt.second <= 2:
            self._mos_last_date = today
            self._mos_active = True

            if self.right_mode != "candle" and not self.settings_open:
                self._show_right("candle")

            duration_sec = 60
            p = self._resolve_path(self.minute_of_silence_sound_path)
            if p and os.path.exists(p):
                try:
                    snd = pygame.mixer.Sound(p)
                    duration_sec = max(5, int(snd.get_length()) + 1)
                except Exception:
                    duration_sec = 60

            self._mos_end_time = now_dt + timedelta(seconds=duration_sec)

            if not self.silent_mode:
                self._play_sound(self.minute_of_silence_sound_path)

    def _update_lesson_or_break(self, now_dt: datetime):
        if self._alarm_priority:
            self.progress.set(0)
            self.lesson_now_label.configure(text="ТРИВОГА\nГОЛОВНА")
            return

        if self._mos_active:
            self.progress.set(0)
            self.lesson_now_label.configure(text="ХВИЛИНА\nМОВЧАННЯ")
            return

        lessons = [x for x in self.schedule if is_hhmm(x.get("start", "")) and is_hhmm(x.get("end", ""))]
        lessons.sort(key=lambda x: hhmm_to_seconds(x["start"]))

        now_sec = now_dt.hour * 3600 + now_dt.minute * 60 + now_dt.second

        for it in lessons:
            s = hhmm_to_seconds(it["start"])
            e = hhmm_to_seconds(it["end"])
            if s <= now_sec < e:
                left = e - now_sec
                total = max(1, e - s)
                done = max(0, min(total, now_sec - s))
                self.progress.set(done / total)
                self.lesson_now_label.configure(text=f"{it['n']} УРОК\n {seconds_to_hhmmss(left)}")
                return

        for i in range(len(lessons) - 1):
            a = lessons[i]
            b = lessons[i + 1]
            a_end = hhmm_to_seconds(a["end"])
            b_start = hhmm_to_seconds(b["start"])
            if a_end <= now_sec < b_start:
                left = b_start - now_sec
                total = max(1, b_start - a_end)
                done = max(0, min(total, now_sec - a_end))
                self.progress.set(done / total)
                self.lesson_now_label.configure(text=f"ПЕРЕРВА\n{seconds_to_hhmmss(left)}")
                return

        if lessons and now_sec < hhmm_to_seconds(lessons[0]["start"]):
            left = hhmm_to_seconds(lessons[0]["start"]) - now_sec
            self.progress.set(0)
            self.lesson_now_label.configure(text=f"ДО 1 УРОКУ\n{seconds_to_hhmmss(left)}")
            return

        self.progress.set(0)
        self.lesson_now_label.configure(text="КІНЕЦЬ\nУРОКІВ")

    def _worker_loop(self):
        while not self._worker_stop.is_set():
            now_dt = self._now_dt()
            hhmm = now_dt.strftime("%H:%M")
            sec = now_dt.second
            today = now_dt.date()

            # щоденний ресет антидублю
            if self._bell_fired_date != today:
                self._bell_fired_date = today
                self._bell_fired_keys.clear()

            if self.shutdown_enabled and is_hhmm(self.shutdown_time):
                if hhmm == self.shutdown_time and sec == 0 and self._shutdown_last_date != today:
                    self._shutdown_last_date = today
                    try:
                        subprocess.Popen(["shutdown", "/s", "/t", "0"], shell=False)
                    except Exception:
                        pass

            # ВИПРАВЛЕНО: спрацьовування дзвінків рівно 1 раз на подію
            if not self._alarm_priority and not self._mos_active and not self.silent_mode:
                if sec == 0:
                    for it in self.schedule:
                        if not (is_hhmm(it.get("start", "")) and is_hhmm(it.get("end", ""))):
                            continue
                        n = it.get("n", "?")

                        if hhmm == it["start"]:
                            key = f"{today}|{hhmm}|start|{n}"
                            if key not in self._bell_fired_keys:
                                self._bell_fired_keys.add(key)
                                # If a custom recording is attached to start, play it, else play default start sound
                                rec_name = it.get("recording_start", "")
                                if rec_name and rec_name in self.custom_recordings:
                                    try:
                                        threading.Thread(target=self._play_recording, args=(rec_name,), daemon=True).start()
                                    except Exception:
                                        pass
                                else:
                                    self._play_sound(self.lesson_start_sound_path)

                        if hhmm == it["end"]:
                            key = f"{today}|{hhmm}|end|{n}"
                            if key not in self._bell_fired_keys:
                                self._bell_fired_keys.add(key)
                                rec_name = it.get("recording_end", "")
                                if rec_name and rec_name in self.custom_recordings:
                                    try:
                                        threading.Thread(target=self._play_recording, args=(rec_name,), daemon=True).start()
                                    except Exception:
                                        pass
                                else:
                                    self._play_sound(self.lesson_end_sound_path)

            time.sleep(0.20)

    def _show_alarm_overlay(self):
        if self._alarm_overlay_on:
            return
        self._alarm_overlay_on = True
        self._alarm_priority = True
        self._stop_all_non_alarm_audio()
        self.alarm_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.alarm_overlay.lift()
        self._start_siren()

    def _hide_alarm_overlay(self):
        self._alarm_overlay_on = False
        self._alarm_priority = False
        self.alarm_overlay.place_forget()
        self._stop_siren()

    def _poll_air_alert(self):
        try:
            self.ALERTS_TOKEN = self.token_var.get().strip()
            self.ALERT_UID = safe_int(self.uid_var.get().strip(), self.ALERT_UID)

            if not self.ALERTS_TOKEN or not self.ALERT_UID:
                self.after(7000, self._poll_air_alert)
                return

            url = f"https://api.alerts.in.ua/v1/iot/active_air_raid_alerts/{self.ALERT_UID}.json"
            headers = {"Authorization": f"Bearer {self.ALERTS_TOKEN}"}
            r = requests.get(url, headers=headers, timeout=6)

            if r.status_code != 200:
                self.after(7000, self._poll_air_alert)
                return

            status = r.text.strip().strip('"')
            if status in ("A", "P"):
                self._show_alarm_overlay()
            else:
                self._hide_alarm_overlay()
        except Exception:
            pass

        self.after(7000, self._poll_air_alert)

    def _enable_test_time(self):
        s = (self.test_time_var.get() or "").strip()
        if not is_hhmm(s):
            messagebox.showerror("Помилка", "Введи час у форматі HH:MM, наприклад 08:40")
            return
        real = now_local()
        h, m = map(int, s.split(":"))
        target = real.replace(hour=h, minute=m, second=real.second, microsecond=real.microsecond)
        self._time_offset = target - real
        self.test_mode_on = True
        self._save_config()
        messagebox.showinfo("Ок", f"Тест-час увімкнено: {s}")

    def _disable_test_time(self):
        self._time_offset = timedelta(0)
        self.test_mode_on = False
        self._save_config()
        messagebox.showinfo("Ок", "Тест-час вимкнено.")

    def _load_config(self):
        if not self.config_path.exists():
            self._apply_defaults()
            self._save_config()
            return

        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            self._apply_defaults()
            self._save_config()
            return

        def getv(k):
            return data.get(k, DEFAULTS.get(k))

        self.photo_path = getv("photo_path") or ""
        if self.photo_path:
            p = self._resolve_path(self.photo_path)
            if p and os.path.exists(p):
                try:
                    self.photo_img_original = Image.open(p).convert("RGBA")
                except Exception:
                    self.photo_img_original = None

        self.lesson_start_sound_path = getv("lesson_start_sound_path") or ""
        self.lesson_end_sound_path = getv("lesson_end_sound_path") or ""
        self.siren_sound_path = getv("siren_sound_path") or ""
        self.minute_of_silence_sound_path = getv("minute_of_silence_sound_path") or ""

        # Load custom recordings
        self.custom_recordings = getv("custom_recordings") or {}

        self.ALERTS_TOKEN = getv("ALERTS_TOKEN") or ""
        self.ALERT_UID = safe_int(getv("ALERT_UID"), 0)

        self.minute_of_silence_enabled = bool(getv("minute_of_silence_enabled"))
        self.candle_gif_path = getv("candle_gif_path") or ""
        self.silent_mode = bool(getv("silent_mode"))

        self.entry_lock_enabled = bool(getv("entry_lock_enabled"))
        self.entry_password = getv("entry_password") or ""

        self.shutdown_enabled = bool(getv("shutdown_enabled"))
        st = getv("shutdown_time") or "00:00"
        self.shutdown_time = st if is_hhmm(st) else "00:00"

        self.hibernation_enabled = bool(getv("hibernation_enabled"))
        ht = getv("hibernation_time") or "00:00"
        self.hibernation_time = ht if is_hhmm(ht) else "00:00"

        self.autostart_enabled = bool(getv("autostart_enabled"))

        sch = data.get("schedule", None)
        if isinstance(sch, list) and sch:
            cleaned = []
            for it in sch:
                if isinstance(it, dict) and "n" in it and "start" in it and "end" in it:
                    if is_hhmm(str(it["start"])) and is_hhmm(str(it["end"])):
                        cleaned.append({"n": int(it["n"]), "start": str(it["start"]), "end": str(it["end"])})
            self.schedule = cleaned if cleaned else [dict(x) for x in DEFAULT_SCHEDULE_12]
        else:
            self.schedule = [dict(x) for x in DEFAULT_SCHEDULE_12]

        self.test_mode_on = bool(getv("test_mode_on"))
        off = safe_int(getv("test_offset_seconds"), 0)
        self._time_offset = timedelta(seconds=int(off)) if self.test_mode_on else timedelta(0)

        p = self._resolve_path(self.siren_sound_path)
        if p and os.path.exists(p):
            try:
                self._siren_sound = pygame.mixer.Sound(p)
                self._siren_sound.set_volume(1.0)
            except Exception:
                self._siren_sound = None

        self._load_gif_frames()

    def _apply_defaults(self):
        for k, v in DEFAULTS.items():
            setattr(self, k, v)
        self.schedule = [dict(x) for x in DEFAULT_SCHEDULE_12]

    def _save_config(self):
        try:
            if hasattr(self, "token_var"):
                self.ALERTS_TOKEN = self.token_var.get().strip()
            if hasattr(self, "uid_var"):
                self.ALERT_UID = safe_int(self.uid_var.get().strip(), self.ALERT_UID)

            data = {
                "photo_path": self.photo_path,
                "lesson_start_sound_path": self.lesson_start_sound_path,
                "lesson_end_sound_path": self.lesson_end_sound_path,
                "siren_sound_path": self.siren_sound_path,
                "minute_of_silence_sound_path": self.minute_of_silence_sound_path,
                "ALERTS_TOKEN": self.ALERTS_TOKEN,
                "ALERT_UID": self.ALERT_UID,
                "minute_of_silence_enabled": self.minute_of_silence_enabled,
                "candle_gif_path": self.candle_gif_path,
                "silent_mode": self.silent_mode,
                "test_mode_on": self.test_mode_on,
                "test_offset_seconds": int(self._time_offset.total_seconds()),
                "entry_lock_enabled": self.entry_lock_enabled,
                "entry_password": self.entry_password,
                "shutdown_enabled": self.shutdown_enabled,
                "shutdown_time": self.shutdown_time,
                "hibernation_enabled": self.hibernation_enabled,
                "hibernation_time": self.hibernation_time,
                "autostart_enabled": self.autostart_enabled,
                "schedule": self.schedule,
                "custom_recordings": self.custom_recordings,
            }
            self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        if hasattr(self, "btn_pick_start"):
            self._refresh_sound_button_titles()

    def _get_recordings_dir(self):
        """Повертає папку для записів"""
        rec_dir = self.base_dir / "recordings"
        rec_dir.mkdir(exist_ok=True)
        return rec_dir
    
    def _start_recording(self):
        """Запускає запис звуку"""
        self.is_recording = True
        self.record_data = []
        self.record_start_time = time.time()
        
        def record_thread():
            try:
                sr = 44100
                duration = 60  # Макс 60 секунд
                recording = sd.rec(int(sr * duration), samplerate=sr, channels=1, dtype=np.int16)
                sd.wait()
                self.record_data = recording
            except Exception as e:
                messagebox.showerror("Помилка запису", f"Помилка при записі: {e}")
            finally:
                self.is_recording = False
        
        thread = threading.Thread(target=record_thread, daemon=True)
        thread.start()
    
    def _stop_recording(self):
        """Зупиняє запис звуку"""
        try:
            sd.stop()
        except Exception:
            pass
    
    def _save_recording(self, name: str):
        """Зберігає запис звуку"""
        if not self.record_data or len(self.record_data) == 0:
            messagebox.showwarning("Помилка", "Нема записованого звуку!")
            return False
        
        try:
            rec_dir = self._get_recordings_dir()
            filename = f"{name}.wav"
            filepath = rec_dir / filename
            
            sr = 44100
            wavfile.write(str(filepath), sr, self.record_data.astype(np.int16))
            
            self.custom_recordings[name] = {
                "path": str(filepath),
                "created": datetime.now().isoformat(),
                "used_in_schedule": []
            }
            self._save_config()
            messagebox.showinfo("Успіх", f"Запис '{name}' збережено!")
            return True
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка при збережені: {e}")
            return False
    
    def _play_recording(self, name: str):
        """Відтворює записаний звук"""
        try:
            if name not in self.custom_recordings:
                messagebox.showerror("Помилка", "Запис не знайдено!")
                return
            
            filepath = self.custom_recordings[name]["path"]
            if not os.path.exists(filepath):
                messagebox.showerror("Помилка", "Файл запису не знайдено!")
                return
            
            sr, data = wavfile.read(filepath)
            sd.play(data, sr)
            sd.wait()
        except Exception as e:
            messagebox.showerror("Помилка при відтворенні", str(e))
    
    def _delete_recording(self, name: str):
        """Видаляє запис"""
        try:
            if name not in self.custom_recordings:
                return False
            
            filepath = self.custom_recordings[name]["path"]
            if os.path.exists(filepath):
                os.remove(filepath)
            
            del self.custom_recordings[name]
            self._save_config()
            return True
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка при видаленні: {e}")
            return False
    
    def _rename_recording(self, old_name: str, new_name: str):
        """Перейменовує запис"""
        try:
            if old_name not in self.custom_recordings:
                return False
            
            self.custom_recordings[new_name] = self.custom_recordings.pop(old_name)
            self._save_config()
            return True
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка при перейменуванні: {e}")
            return False

    def _build_recordings_panel(self):
        """Будує панель для управління записами"""
        p = self.panel_recordings
        
        # Заголовок
        header = ctk.CTkLabel(p, text="Мої записи", font=ctk.CTkFont(size=18, weight="bold"))
        header.grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 10), sticky="w")
        
        # Кнопки для запису
        btn_frame = ctk.CTkFrame(p, corner_radius=12)
        btn_frame.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 10), sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        
        self.btn_start_rec = ctk.CTkButton(btn_frame, text="▶ Почати запис", command=self._start_rec_window)
        self.btn_start_rec.grid(row=0, column=0, padx=(0, 5), pady=10, sticky="ew")
        
        self.btn_stop_rec = ctk.CTkButton(btn_frame, text="⏹ Зберегти запис", command=self._stop_rec_window, state="disabled")
        self.btn_stop_rec.grid(row=0, column=1, padx=(5, 0), pady=10, sticky="ew")
        
        # Список записів
        self.recordings_list_frame = ctk.CTkFrame(p, corner_radius=12)
        self.recordings_list_frame.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 18), sticky="nsew")
        self.recordings_list_frame.grid_columnconfigure(0, weight=1)
        self.recordings_list_frame.grid_rowconfigure(0, weight=1)
        
        self.recordings_list = ctk.CTkScrollableFrame(self.recordings_list_frame, corner_radius=12)
        self.recordings_list.grid(row=0, column=0, sticky="nsew")
        self.recordings_list.grid_columnconfigure(0, weight=1)
        
        self._refresh_recordings_list()
    
    def _refresh_recordings_list(self):
        """Оновлює список записів"""
        for widget in self.recordings_list.winfo_children():
            widget.destroy()
        
        if not self.custom_recordings:
            empty_label = ctk.CTkLabel(self.recordings_list, text="Нема записів", text_color="gray")
            empty_label.pack(padx=10, pady=20)
            return
        
        for name in self.custom_recordings.keys():
            self._add_recording_item(name)
    
    def _add_recording_item(self, name: str):
        """Додає запис до списку"""
        item_frame = ctk.CTkFrame(self.recordings_list, corner_radius=10)
        item_frame.pack(fill="x", padx=10, pady=5)
        item_frame.grid_columnconfigure(1, weight=1)
        
        # Іконка запису
        icon_label = ctk.CTkLabel(item_frame, text="🎙", font=ctk.CTkFont(size=16))
        icon_label.grid(row=0, column=0, padx=10, pady=10)
        
        # Назва запису
        name_label = ctk.CTkLabel(item_frame, text=name, font=ctk.CTkFont(size=14))
        name_label.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="w")
        
        # Кнопки дій
        play_btn = ctk.CTkButton(item_frame, text="▶", width=40, command=lambda: self._play_recording(name))
        play_btn.grid(row=0, column=2, padx=2, pady=10)
        
        rename_btn = ctk.CTkButton(item_frame, text="✏", width=40, command=lambda: self._show_rename_dialog(name))
        rename_btn.grid(row=0, column=3, padx=2, pady=10)
        
        delete_btn = ctk.CTkButton(item_frame, text="🗑", width=40, fg_color="#8b2b2b", hover_color="#a43737", 
                                  command=lambda: self._delete_recording_with_refresh(name))
        delete_btn.grid(row=0, column=4, padx=2, pady=10)
    
    def _start_rec_window(self):
        """Відкриває вікно для запису"""
        self._stop_recording()
        self.is_recording = True
        self.btn_start_rec.configure(state="disabled")
        self.btn_stop_rec.configure(state="normal")
        self._start_recording()
        messagebox.showinfo("Запис", "Запис розпочато! Говори в мікрофон.")
    
    def _stop_rec_window(self):
        """Зупиняє запис і пропонує назву"""
        self._stop_recording()
        self.btn_start_rec.configure(state="normal")
        self.btn_stop_rec.configure(state="disabled")
        
        name = simpledialog.askstring("Назва запису", "Введи назву для цього запису:")
        if name and name.strip():
            if self._save_recording(name.strip()):
                self._refresh_recordings_list()
    
    def _show_rename_dialog(self, old_name: str):
        """Показує діалог перейменування"""
        new_name = simpledialog.askstring("Перейменувати", f"Нова назва для '{old_name}':", initialvalue=old_name)
        if new_name and new_name.strip() and new_name != old_name:
            if self._rename_recording(old_name, new_name.strip()):
                self._refresh_recordings_list()
    
    def _delete_recording_with_refresh(self, name: str):
        """Видаляє запис з оновленням списку"""
        if messagebox.askyesno("Видалення", f"Видалити запис '{name}'?"):
            if self._delete_recording(name):
                self._refresh_recordings_list()

    def on_close(self):
        self._worker_stop.set()
        self._worker_stop.set()
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self._stop_siren()
        self._stop_candle_gif()
        self._save_config()
        self.destroy()


if __name__ == "__main__":
    app = SchoolBellApp()
    app.mainloop()
