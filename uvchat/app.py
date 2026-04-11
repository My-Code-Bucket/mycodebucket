#!/usr/bin/env python3
import json
import os
import re
import shutil
import threading
import tkinter as tk
import ctypes
import ctypes.wintypes as wintypes
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
CONFIG_EXAMPLE_PATH = BASE_DIR / "config.example.json"
DEBUG_CAPTURE_DIR = BASE_DIR / "debug_captures"
WINDOWS_TESSERACT_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]
DEFAULT_SCREEN_WIDTH = 1920
DEFAULT_SCREEN_HEIGHT = 1200
TABS_CAPTURE_HEIGHT = 28
DEFAULT_WINDOW_TITLE_HINT = "Utherverse 3D Client"


DEFAULT_CONFIG = {
    "capture": {"x": 0, "y": 0, "width": 600, "height": 300},
    "tabs_capture": {"x": 0, "y": 272, "width": 600, "height": 28},
    "capture_backend": "auto",
    "poll_interval_ms": 1500,
    "ocr_lang": "eng",
    "ocr_profile": "uvchat",
    "tesseract_cmd": "",
    "ocr_psm": 6,
    "source_language": "auto",
    "target_language": "de",
    "translation": {
        "mode": "echo",
        "libretranslate_url": "http://127.0.0.1:5000/translate",
        "google_api_key": "",
        "oci_config_file": str(Path.home() / ".oci" / "config"),
        "oci_profile": "DEFAULT",
        "oci_compartment_id": "",
        "api_key": "",
    },
    "window_tracking": {
        "enabled": True,
        "title_hint": DEFAULT_WINDOW_TITLE_HINT,
        "chat_relative": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        "tabs_relative": {"x": 0.0, "y": 0.906667, "width": 1.0, "height": 0.093333},
    },
    "window": {"always_on_top": True, "width": 520, "height": 860},
}


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def deep_merge(base, override):
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    config = dict(DEFAULT_CONFIG)
    if CONFIG_EXAMPLE_PATH.exists():
        with CONFIG_EXAMPLE_PATH.open("r", encoding="utf-8") as fh:
            config = deep_merge(config, json.load(fh))
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            config = deep_merge(config, json.load(fh))
    return config


def save_config(config):
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)


class UvChatApp:
    CHAT_LINE_PATTERN = re.compile(r"^\[\d{2}:\d{2}\]\s+[A-Za-z0-9_]+:")
    TIMESTAMP_PATTERN = re.compile(r"^\[\d{2}:\d{2}\]")

    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.is_running = False
        self.is_busy = False
        self.original_history_lines = []
        self.translated_history_lines = []
        self.seen_chat_lines = set()
        self.chat_histories = {"LOCAL": {"original": [], "translated": [], "seen": set()}}
        self.active_tab_name = "LOCAL"
        self.region_picker = None
        self.region_picker_canvas = None
        self.region_picker_start = None
        self.region_picker_rect = None
        self.region_picker_origin = None
        self.region_picker_target = "capture"
        self.capture_preview_image = None
        self.processed_preview_image = None
        self.tabs_preview_image = None
        self.last_capture_image = None
        self.last_processed_image = None
        self.last_tabs_capture_image = None

        self.root.title("uvchat")
        self.root.geometry(
            f"{self.config['window']['width']}x{self.config['window']['height']}"
        )
        self.root.attributes("-topmost", self.config["window"]["always_on_top"])

        self._build_ui()
        self._apply_config_to_ui()
        self._set_status("Ready. Configure the capture region and press Start.")

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        top = ttk.Frame(self.root, padding=12)
        top.grid(row=0, column=0, sticky="ew")
        for i in range(4):
            top.columnconfigure(i, weight=1)

        self.x_var = tk.StringVar()
        self.y_var = tk.StringVar()
        self.w_var = tk.StringVar()
        self.h_var = tk.StringVar()
        self.tabs_x_var = tk.StringVar()
        self.tabs_y_var = tk.StringVar()
        self.tabs_w_var = tk.StringVar()
        self.tabs_h_var = tk.StringVar()
        self.poll_var = tk.StringVar()
        self.ocr_lang_var = tk.StringVar()
        self.source_lang_var = tk.StringVar()
        self.target_lang_var = tk.StringVar()
        self.topmost_var = tk.BooleanVar()
        self.controls_collapsed_var = tk.BooleanVar(value=True)
        self.translation_mode_var = tk.StringVar()
        self.libre_url_var = tk.StringVar()
        self.libre_api_key_var = tk.StringVar()
        self.google_api_key_var = tk.StringVar()
        self.oci_config_file_var = tk.StringVar()
        self.oci_profile_var = tk.StringVar()
        self.oci_compartment_var = tk.StringVar()
        self.window_tracking_var = tk.BooleanVar()
        self.window_title_var = tk.StringVar()

        header = ttk.Frame(top)
        header.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Settings").grid(row=0, column=0, sticky="w")
        self.collapse_button = ttk.Button(
            header,
            text="Show Controls",
            command=self._toggle_controls_visibility,
        )
        self.collapse_button.grid(row=0, column=1, sticky="e")

        self.controls_frame = ttk.Frame(top)
        self.controls_frame.grid(row=1, column=0, columnspan=4, sticky="ew")
        for i in range(4):
            self.controls_frame.columnconfigure(i, weight=1)

        fields = [
            ("X", self.x_var, 0, 0),
            ("Y", self.y_var, 0, 1),
            ("Width", self.w_var, 0, 2),
            ("Height", self.h_var, 0, 3),
            ("Tabs X", self.tabs_x_var, 2, 0),
            ("Tabs Y", self.tabs_y_var, 2, 1),
            ("Tabs W", self.tabs_w_var, 2, 2),
            ("Tabs H", self.tabs_h_var, 2, 3),
            ("Poll ms", self.poll_var, 4, 0),
            ("OCR", self.ocr_lang_var, 4, 1),
            ("Source", self.source_lang_var, 4, 2),
            ("Target", self.target_lang_var, 4, 3),
        ]

        for label, variable, row, column in fields:
            ttk.Label(self.controls_frame, text=label).grid(
                row=row, column=column, sticky="w", padx=4
            )
            ttk.Entry(self.controls_frame, textvariable=variable, width=8).grid(
                row=row + 1, column=column, sticky="ew", padx=4, pady=(2, 8)
            )

        ttk.Label(self.controls_frame, text="Mode").grid(row=6, column=0, sticky="w", padx=4)
        ttk.Combobox(
            self.controls_frame,
            textvariable=self.translation_mode_var,
            values=["echo", "libretranslate", "google", "oci"],
            state="readonly",
            width=12,
        ).grid(row=7, column=0, sticky="ew", padx=4)

        ttk.Label(self.controls_frame, text="LibreTranslate URL").grid(
            row=6, column=1, columnspan=2, sticky="w", padx=4
        )
        ttk.Entry(self.controls_frame, textvariable=self.libre_url_var).grid(
            row=7, column=1, columnspan=2, sticky="ew", padx=4
        )

        ttk.Label(self.controls_frame, text="Libre API Key").grid(
            row=9, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 0)
        )
        ttk.Entry(
            self.controls_frame,
            textvariable=self.libre_api_key_var,
            show="*",
        ).grid(row=10, column=0, columnspan=4, sticky="ew", padx=4, pady=(2, 0))

        ttk.Label(self.controls_frame, text="Google API Key").grid(
            row=11, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 0)
        )
        ttk.Entry(
            self.controls_frame,
            textvariable=self.google_api_key_var,
            show="*",
        ).grid(row=12, column=0, columnspan=4, sticky="ew", padx=4, pady=(2, 0))

        ttk.Label(self.controls_frame, text="OCI Config").grid(
            row=13, column=0, sticky="w", padx=4, pady=(8, 0)
        )
        ttk.Entry(
            self.controls_frame,
            textvariable=self.oci_config_file_var,
        ).grid(row=14, column=0, columnspan=2, sticky="ew", padx=4, pady=(2, 0))

        ttk.Label(self.controls_frame, text="OCI Profile").grid(
            row=13, column=2, sticky="w", padx=4, pady=(8, 0)
        )
        ttk.Entry(
            self.controls_frame,
            textvariable=self.oci_profile_var,
        ).grid(row=14, column=2, sticky="ew", padx=4, pady=(2, 0))

        ttk.Label(self.controls_frame, text="OCI Compartment OCID").grid(
            row=15, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 0)
        )
        ttk.Entry(
            self.controls_frame,
            textvariable=self.oci_compartment_var,
        ).grid(row=16, column=0, columnspan=4, sticky="ew", padx=4, pady=(2, 0))

        ttk.Checkbutton(
            self.controls_frame,
            text="Always On Top",
            variable=self.topmost_var,
            command=self._toggle_topmost,
        ).grid(row=7, column=3, sticky="w", padx=4)

        ttk.Checkbutton(
            self.controls_frame,
            text="Track Utherverse Window",
            variable=self.window_tracking_var,
        ).grid(row=17, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 0))

        ttk.Label(self.controls_frame, text="Window Title").grid(
            row=17, column=2, columnspan=2, sticky="w", padx=4, pady=(8, 0)
        )
        ttk.Entry(self.controls_frame, textvariable=self.window_title_var).grid(
            row=18, column=2, columnspan=2, sticky="ew", padx=4, pady=(2, 0)
        )

        controls = ttk.Frame(self.controls_frame)
        controls.grid(row=19, column=0, columnspan=4, sticky="ew", padx=4, pady=(10, 0))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        self.pick_region_button = ttk.Button(
            controls, text="Pick Chat Region", command=self.pick_region
        )
        self.pick_region_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))

        self.pick_tabs_region_button = ttk.Button(
            controls, text="Tabs From Chat", command=self.sync_tabs_capture_from_chat
        )
        self.pick_tabs_region_button.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        self.detect_window_button = ttk.Button(
            controls, text="Detect Window", command=self.detect_window_from_ui
        )
        self.detect_window_button.grid(row=1, column=0, sticky="ew", padx=(0, 6))

        self.sync_offsets_button = ttk.Button(
            controls, text="Use Current As Offsets", command=self.sync_offsets_from_current_region
        )
        self.sync_offsets_button.grid(row=1, column=1, sticky="ew")

        self.save_button = ttk.Button(
            controls, text="Save Config", command=self.save_current_config
        )
        self.save_button.grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=(6, 0))

        self.debug_capture_button = ttk.Button(
            controls, text="Save Debug Capture", command=self.save_debug_capture
        )
        self.debug_capture_button.grid(row=2, column=1, sticky="ew", pady=(6, 0))

        self.clear_chat_button = ttk.Button(
            controls, text="Clear Chat", command=self.clear_chat
        )
        self.clear_chat_button.grid(row=3, column=0, sticky="ew", padx=(0, 6), pady=(6, 0))

        self.start_button = ttk.Button(
            controls, text="Start Scanning", command=self.start_scan
        )
        self.start_button.grid(row=3, column=1, sticky="ew", pady=(6, 0))

        self.stop_button = ttk.Button(
            controls, text="Stop Scanning", command=self.stop_scan
        )
        self.stop_button.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._sync_controls_visibility()

        status_frame = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        status_frame.grid(row=1, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar()
        ttk.Label(
            status_frame, textvariable=self.status_var, foreground="#c98200"
        ).grid(row=0, column=0, sticky="w")
        self.active_tab_var = tk.StringVar(value="Active tab: LOCAL")
        ttk.Label(
            status_frame, textvariable=self.active_tab_var, foreground="#4a6fa5"
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.window_info_var = tk.StringVar(value="Window: not detected")
        ttk.Label(
            status_frame, textvariable=self.window_info_var, foreground="#6a6a6a"
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        panes = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        panes.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))

        preview_frame = ttk.LabelFrame(panes, text="Capture Preview")
        original_frame = ttk.LabelFrame(panes, text="Original OCR")
        translated_frame = ttk.LabelFrame(panes, text="Translated")

        self.capture_preview_label = ttk.Label(
            preview_frame,
            text="No capture yet.",
            anchor="w",
            justify="left",
        )
        self.capture_preview_label.pack(fill="x", padx=8, pady=(8, 4))

        preview_images = ttk.Frame(preview_frame)
        preview_images.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        preview_images.columnconfigure(0, weight=1)
        preview_images.rowconfigure(0, weight=1)
        preview_images.rowconfigure(1, weight=1)

        raw_frame = ttk.LabelFrame(preview_images, text="Raw Capture")
        raw_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        processed_frame = ttk.LabelFrame(preview_images, text="OCR Preview")
        processed_frame.grid(row=1, column=0, sticky="nsew")
        tabs_frame = ttk.LabelFrame(preview_images, text="Tabs Preview")
        tabs_frame.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        preview_images.rowconfigure(2, weight=1)

        self.capture_preview_image_label = ttk.Label(
            raw_frame,
            text="No raw capture yet.",
            anchor="center",
            justify="center",
        )
        self.capture_preview_image_label.pack(fill="both", expand=True, padx=6, pady=6)

        self.processed_preview_image_label = ttk.Label(
            processed_frame,
            text="No OCR preview yet.",
            anchor="center",
            justify="center",
        )
        self.processed_preview_image_label.pack(fill="both", expand=True, padx=6, pady=6)

        self.tabs_preview_image_label = ttk.Label(
            tabs_frame,
            text="No tabs preview yet.",
            anchor="center",
            justify="center",
        )
        self.tabs_preview_image_label.pack(fill="both", expand=True, padx=6, pady=6)

        self.original_text = ScrolledText(
            original_frame, wrap="word", font=("TkDefaultFont", 11)
        )
        self.original_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.translated_text = ScrolledText(
            translated_frame, wrap="word", font=("TkDefaultFont", 11)
        )
        self.translated_text.pack(fill="both", expand=True, padx=8, pady=8)

        panes.add(preview_frame, weight=1)
        panes.add(original_frame, weight=1)
        panes.add(translated_frame, weight=1)

    def _apply_config_to_ui(self):
        capture = self.config["capture"]
        tabs_capture = self.config.get("tabs_capture", self._derive_tabs_capture(capture))
        self.x_var.set(str(capture["x"]))
        self.y_var.set(str(capture["y"]))
        self.w_var.set(str(capture["width"]))
        self.h_var.set(str(capture["height"]))
        self.tabs_x_var.set(str(tabs_capture["x"]))
        self.tabs_y_var.set(str(tabs_capture["y"]))
        self.tabs_w_var.set(str(tabs_capture["width"]))
        self.tabs_h_var.set(str(tabs_capture["height"]))
        self.poll_var.set(str(self.config["poll_interval_ms"]))
        self.ocr_lang_var.set(self.config["ocr_lang"])
        self.source_lang_var.set(self.config["source_language"])
        self.target_lang_var.set(self.config["target_language"])
        self.topmost_var.set(self.config["window"]["always_on_top"])
        self.translation_mode_var.set(self.config["translation"]["mode"])
        self.libre_url_var.set(self.config["translation"]["libretranslate_url"])
        self.libre_api_key_var.set(self.config["translation"].get("api_key", ""))
        self.google_api_key_var.set(self.config["translation"].get("google_api_key", ""))
        self.oci_config_file_var.set(self.config["translation"].get("oci_config_file", ""))
        self.oci_profile_var.set(self.config["translation"].get("oci_profile", "DEFAULT"))
        self.oci_compartment_var.set(self.config["translation"].get("oci_compartment_id", ""))
        self.window_tracking_var.set(self.config.get("window_tracking", {}).get("enabled", True))
        self.window_title_var.set(
            self.config.get("window_tracking", {}).get("title_hint", DEFAULT_WINDOW_TITLE_HINT)
        )
        self._update_scan_buttons()

    def _read_ui_into_config(self):
        self.config["capture"] = {
            "x": int(self.x_var.get() or "0"),
            "y": int(self.y_var.get() or "0"),
            "width": int(self.w_var.get() or "0"),
            "height": int(self.h_var.get() or "0"),
        }
        self.config["tabs_capture"] = {
            "x": int(self.tabs_x_var.get() or "0"),
            "y": int(self.tabs_y_var.get() or "0"),
            "width": int(self.tabs_w_var.get() or "0"),
            "height": int(self.tabs_h_var.get() or "0"),
        }
        self.config["poll_interval_ms"] = int(self.poll_var.get() or "1500")
        self.config["ocr_lang"] = self.ocr_lang_var.get().strip() or "eng"
        self.config["source_language"] = self.source_lang_var.get().strip() or "auto"
        self.config["target_language"] = self.target_lang_var.get().strip() or "de"
        self.config["translation"]["mode"] = self.translation_mode_var.get().strip() or "echo"
        self.config["translation"]["libretranslate_url"] = self.libre_url_var.get().strip()
        self.config["translation"]["api_key"] = self.libre_api_key_var.get().strip()
        self.config["translation"]["google_api_key"] = self.google_api_key_var.get().strip()
        self.config["translation"]["oci_config_file"] = self.oci_config_file_var.get().strip()
        self.config["translation"]["oci_profile"] = self.oci_profile_var.get().strip() or "DEFAULT"
        self.config["translation"]["oci_compartment_id"] = self.oci_compartment_var.get().strip()
        self.config["window_tracking"]["enabled"] = bool(self.window_tracking_var.get())
        self.config["window_tracking"]["title_hint"] = (
            self.window_title_var.get().strip() or DEFAULT_WINDOW_TITLE_HINT
        )
        self.config["window"]["always_on_top"] = bool(self.topmost_var.get())

    def _screen_size(self):
        width = self.root.winfo_screenwidth() or DEFAULT_SCREEN_WIDTH
        height = self.root.winfo_screenheight() or DEFAULT_SCREEN_HEIGHT
        return width, height

    def _derive_tabs_capture(self, capture=None):
        capture = capture or self.config["capture"]
        screen_width, screen_height = self._screen_size()
        x = max(0, min(int(capture["x"]), max(0, screen_width - 1)))
        width = max(1, min(int(capture["width"]), max(1, screen_width - x)))
        height = TABS_CAPTURE_HEIGHT
        y = int(capture["y"]) + int(capture["height"]) - height
        y = max(0, min(y, max(0, screen_height - height)))
        return {"x": x, "y": y, "width": width, "height": height}

    def sync_tabs_capture_from_chat(self):
        tabs_capture = self._derive_tabs_capture(
            {
                "x": int(self.x_var.get() or "0"),
                "y": int(self.y_var.get() or "0"),
                "width": int(self.w_var.get() or "0"),
                "height": int(self.h_var.get() or "0"),
            }
        )
        self.tabs_x_var.set(str(tabs_capture["x"]))
        self.tabs_y_var.set(str(tabs_capture["y"]))
        self.tabs_w_var.set(str(tabs_capture["width"]))
        self.tabs_h_var.set(str(tabs_capture["height"]))
        self._set_status(
            "Tabs region synced from chat region: "
            f"x={tabs_capture['x']}, y={tabs_capture['y']}, "
            f"width={tabs_capture['width']}, height={tabs_capture['height']}"
        )

    @staticmethod
    def _rect_to_relative(rect, container):
        width = max(1, int(container["width"]))
        height = max(1, int(container["height"]))
        return {
            "x": round((int(rect["x"]) - int(container["left"])) / width, 6),
            "y": round((int(rect["y"]) - int(container["top"])) / height, 6),
            "width": round(int(rect["width"]) / width, 6),
            "height": round(int(rect["height"]) / height, 6),
        }

    @staticmethod
    def _relative_to_rect(relative, container):
        width = max(1, int(container["width"]))
        height = max(1, int(container["height"]))
        return {
            "x": int(round(int(container["left"]) + float(relative.get("x", 0.0)) * width)),
            "y": int(round(int(container["top"]) + float(relative.get("y", 0.0)) * height)),
            "width": max(1, int(round(float(relative.get("width", 1.0)) * width))),
            "height": max(1, int(round(float(relative.get("height", 1.0)) * height))),
        }

    def _find_target_window_rect(self):
        if os.name != "nt":
            return None
        hint = (
            self.config.get("window_tracking", {}).get("title_hint", DEFAULT_WINDOW_TITLE_HINT)
            or DEFAULT_WINDOW_TITLE_HINT
        ).lower()
        user32 = ctypes.windll.user32
        windows = []
        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, length + 1)
            title = title_buffer.value.strip()
            if not title or hint not in title.lower():
                return True
            rect = RECT()
            if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
                return True
            origin = POINT(rect.left, rect.top)
            if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
                return True
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width <= 0 or height <= 0:
                return True
            windows.append(
                {
                    "title": title,
                    "left": int(origin.x),
                    "top": int(origin.y),
                    "width": width,
                    "height": height,
                }
            )
            return True

        user32.EnumWindows(enum_proc(callback), 0)
        if not windows:
            return None
        windows.sort(key=lambda item: -item["width"] * item["height"])
        return windows[0]

    def detect_window_from_ui(self):
        self._read_ui_into_config()
        window_rect = self._find_target_window_rect()
        if not window_rect:
            self.window_info_var.set("Window: not found")
            self._set_status("Could not find a visible Utherverse window.")
            return
        self.window_info_var.set(
            f"Window: {window_rect['title']} ({window_rect['left']},{window_rect['top']} {window_rect['width']}x{window_rect['height']})"
        )
        self._set_status("Utherverse window detected.")

    def sync_offsets_from_current_region(self):
        self._read_ui_into_config()
        window_rect = self._find_target_window_rect()
        if not window_rect:
            self.window_info_var.set("Window: not found")
            self._set_status("Could not find a visible Utherverse window for offset sync.")
            return
        self.config["window_tracking"]["chat_relative"] = self._rect_to_relative(
            self.config["capture"], window_rect
        )
        self.config["window_tracking"]["tabs_relative"] = self._rect_to_relative(
            self.config["tabs_capture"], window_rect
        )
        self.window_info_var.set(
            f"Window: {window_rect['title']} ({window_rect['left']},{window_rect['top']} {window_rect['width']}x{window_rect['height']})"
        )
        self._set_status("Stored current chat and tabs regions as window-relative offsets.")

    def _apply_window_tracking(self):
        if not self.config.get("window_tracking", {}).get("enabled", True):
            return self.config["capture"], self.config.get("tabs_capture", self._derive_tabs_capture())
        window_rect = self._find_target_window_rect()
        if not window_rect:
            self.window_info_var.set("Window: not found")
            return self.config["capture"], self.config.get("tabs_capture", self._derive_tabs_capture())
        self.window_info_var.set(
            f"Window: {window_rect['title']} ({window_rect['left']},{window_rect['top']} {window_rect['width']}x{window_rect['height']})"
        )
        capture = self._relative_to_rect(
            self.config["window_tracking"].get("chat_relative", {}),
            window_rect,
        )
        tabs_capture = self._relative_to_rect(
            self.config["window_tracking"].get("tabs_relative", {}),
            window_rect,
        )
        return capture, tabs_capture

    def save_current_config(self):
        try:
            self._read_ui_into_config()
            if self.config.get("window_tracking", {}).get("enabled", True):
                window_rect = self._find_target_window_rect()
                if window_rect:
                    self.config["window_tracking"]["chat_relative"] = self._rect_to_relative(
                        self.config["capture"], window_rect
                    )
                    self.config["window_tracking"]["tabs_relative"] = self._rect_to_relative(
                        self.config["tabs_capture"], window_rect
                    )
            save_config(self.config)
            self._set_status(f"Saved config to {CONFIG_PATH}")
        except Exception as exc:
            self._set_status(f"Could not save config: {exc}")

    def _toggle_topmost(self):
        self.root.attributes("-topmost", self.topmost_var.get())

    def _set_status(self, message):
        self.status_var.set(message)

    def _toggle_controls_visibility(self):
        self.controls_collapsed_var.set(not self.controls_collapsed_var.get())
        self._sync_controls_visibility()

    def _sync_controls_visibility(self):
        if self.controls_collapsed_var.get():
            self.controls_frame.grid_remove()
            self.collapse_button.configure(text="Show Controls")
        else:
            self.controls_frame.grid()
            self.collapse_button.configure(text="Hide Controls")

    def _update_scan_buttons(self):
        if self.is_running:
            self.start_button.state(["disabled"])
            self.stop_button.state(["!disabled"])
            self.pick_region_button.state(["disabled"])
            self.pick_tabs_region_button.state(["disabled"])
            self.detect_window_button.state(["disabled"])
            self.sync_offsets_button.state(["disabled"])
        else:
            self.start_button.state(["!disabled"])
            self.stop_button.state(["disabled"])
            self.pick_region_button.state(["!disabled"])
            self.pick_tabs_region_button.state(["!disabled"])
            self.detect_window_button.state(["!disabled"])
            self.sync_offsets_button.state(["!disabled"])

    def save_debug_capture(self):
        if self.last_capture_image is None:
            self._set_status("No capture available yet. Start scanning first.")
            return

        DEBUG_CAPTURE_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        raw_path = DEBUG_CAPTURE_DIR / f"capture-{timestamp}-raw.png"
        processed_path = DEBUG_CAPTURE_DIR / f"capture-{timestamp}-ocr.png"

        self.last_capture_image.save(raw_path)
        if self.last_processed_image is not None:
            self.last_processed_image.save(processed_path)
        tabs_path = None
        if self.last_tabs_capture_image is not None:
            tabs_path = DEBUG_CAPTURE_DIR / f"capture-{timestamp}-tabs.png"
            self.last_tabs_capture_image.save(tabs_path)
        saved_names = [raw_path.name]
        if self.last_processed_image is not None:
            saved_names.append(processed_path.name)
        if tabs_path is not None:
            saved_names.append(tabs_path.name)
        self._set_status(f"Saved debug capture to {', '.join(saved_names)}")

    def clear_chat(self):
        self.original_history_lines = []
        self.translated_history_lines = []
        self.seen_chat_lines = set()
        self.chat_histories = {"LOCAL": {"original": [], "translated": [], "seen": set()}}
        self.active_tab_name = "LOCAL"
        self.active_tab_var.set("Active tab: LOCAL")
        self._set_scrolled_text(self.original_text, "")
        self._set_scrolled_text(self.translated_text, "")
        self._set_status("Cleared chat history.")

    def start_scan(self):
        try:
            self._read_ui_into_config()
            self.root.attributes("-topmost", self.topmost_var.get())
        except Exception as exc:
            self._set_status(f"Invalid config: {exc}")
            return

        if self.is_running:
            self._set_status("Scanner already running.")
            return

        self.is_running = True
        self._update_scan_buttons()
        self._set_status("Scanning started.")
        self.root.after(100, self._scan_tick)

    def stop_scan(self):
        self.is_running = False
        self._update_scan_buttons()
        self._set_status("Scanning stopped.")

    def pick_region(self, target="capture"):
        if self.is_running:
            self._set_status("Stop scanning before picking a new region.")
            return
        if self.region_picker is not None:
            self._set_status("Region picker is already open.")
            return

        self.root.update_idletasks()
        self.root.attributes("-topmost", False)
        self.root.withdraw()

        picker = tk.Toplevel(self.root)
        picker.overrideredirect(True)
        picker.attributes("-topmost", True)
        picker.attributes("-alpha", 0.25)

        left = self.root.winfo_vrootx()
        top = self.root.winfo_vrooty()
        width = self.root.winfo_vrootwidth()
        height = self.root.winfo_vrootheight()
        picker.geometry(f"{width}x{height}+{left}+{top}")
        picker.configure(bg="black")

        canvas = tk.Canvas(
            picker,
            bg="black",
            highlightthickness=0,
            cursor="crosshair",
        )
        canvas.pack(fill="both", expand=True)

        self.region_picker = picker
        self.region_picker_canvas = canvas
        self.region_picker_start = None
        self.region_picker_rect = None
        self.region_picker_origin = (left, top)
        self.region_picker_target = target

        canvas.bind("<ButtonPress-1>", self._on_region_picker_press)
        canvas.bind("<B1-Motion>", self._on_region_picker_drag)
        canvas.bind("<ButtonRelease-1>", self._on_region_picker_release)
        picker.bind("<Escape>", self._cancel_region_picker)
        picker.focus_force()

        self._set_status("Drag over the chat area. Press Escape to cancel.")

    def _on_region_picker_press(self, event):
        self.region_picker_start = (event.x, event.y)
        canvas = self.region_picker_canvas
        if canvas is None:
            return
        if self.region_picker_rect is not None:
            canvas.delete(self.region_picker_rect)
        self.region_picker_rect = canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#00ff66",
            width=3,
        )

    def _on_region_picker_drag(self, event):
        canvas = self.region_picker_canvas
        if canvas is None or self.region_picker_rect is None or self.region_picker_start is None:
            return
        start_x, start_y = self.region_picker_start
        canvas.coords(self.region_picker_rect, start_x, start_y, event.x, event.y)

    def _on_region_picker_release(self, event):
        if self.region_picker_start is None:
            self._close_region_picker()
            return

        start_x, start_y = self.region_picker_start
        end_x = event.x
        end_y = event.y

        picker = self.region_picker
        origin_x = picker.winfo_rootx() if picker is not None else 0
        origin_y = picker.winfo_rooty() if picker is not None else 0

        left = origin_x + min(start_x, end_x)
        top = origin_y + min(start_y, end_y)
        width = abs(end_x - start_x)
        height = abs(end_y - start_y)

        left, top, width, height = self._normalize_capture_coords(left, top, width, height)

        self._close_region_picker()

        if width < 5 or height < 5:
            self._set_status("Region selection was too small.")
            return

        if self.region_picker_target == "tabs_capture":
            self.tabs_x_var.set(str(left))
            self.tabs_y_var.set(str(top))
            self.tabs_w_var.set(str(width))
            self.tabs_h_var.set(str(height))
            self._set_status(
                f"Selected tabs region: x={left}, y={top}, width={width}, height={height}"
            )
        else:
            self.x_var.set(str(left))
            self.y_var.set(str(top))
            self.w_var.set(str(width))
            self.h_var.set(str(height))
            self.sync_tabs_capture_from_chat()
            self._set_status(
                f"Selected chat region: x={left}, y={top}, width={width}, height={height}"
            )

    def _cancel_region_picker(self, _event=None):
        self._close_region_picker()
        self._set_status("Region selection cancelled.")

    def _close_region_picker(self):
        picker = self.region_picker
        self.region_picker = None
        self.region_picker_canvas = None
        self.region_picker_start = None
        self.region_picker_rect = None
        self.region_picker_origin = None
        self.region_picker_target = "capture"

        if picker is not None and picker.winfo_exists():
            picker.destroy()

        self.root.deiconify()
        self.root.attributes("-topmost", self.topmost_var.get())
        self.root.lift()
        self.root.focus_force()

    def _scan_tick(self):
        if not self.is_running:
            return
        if not self.is_busy:
            self.is_busy = True
            threading.Thread(target=self._run_capture_cycle, daemon=True).start()
        self.root.after(self.config["poll_interval_ms"], self._scan_tick)

    def _run_capture_cycle(self):
        try:
            (
                cleaned_text,
                raw_text,
                preview_image,
                processed_image,
                tabs_image,
                active_tab_name,
            ) = self._capture_and_ocr()
            new_lines = self._extract_new_chat_lines(cleaned_text, active_tab_name)
            translated = self._translate_text("\n".join(new_lines)) if new_lines else ""
            self.root.after(
                0,
                lambda: self._update_texts(
                    new_lines,
                    translated,
                    raw_text,
                    preview_image,
                    processed_image,
                    tabs_image,
                    active_tab_name,
                ),
            )
        except Exception as exc:
            self.root.after(0, lambda: self._set_status(f"Scan error: {exc}"))
        finally:
            self.is_busy = False

    def _capture_and_ocr(self):
        try:
            import mss
            from PIL import Image, ImageGrab, ImageOps
            import pytesseract
        except ImportError as exc:
            missing = getattr(exc, "name", str(exc))
            return (
                "Missing dependency.\n\n"
                f"Could not import: {missing}\n"
                "Install packages from requirements.txt plus system OCR packages.\n"
                "Recommended: python3-tk, tesseract-ocr, pillow, mss, pytesseract."
            ), "", None, None, None, self.active_tab_name

        tesseract_cmd = self._find_tesseract_cmd(self.config.get("tesseract_cmd", ""))
        if tesseract_cmd is None:
            return (
                "Tesseract OCR is not installed.\n\n"
                "Install Tesseract OCR for Windows and try again.\n"
                "Expected tesseract.exe in config.json, PATH, the local tools folder, or C:\\Program Files\\Tesseract-OCR."
            ), "", None, None, None, self.active_tab_name
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        tessdata_dir = Path(tesseract_cmd).resolve().parent / "tessdata"
        if tessdata_dir.exists():
            os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)

        capture, tabs_capture = self._apply_window_tracking()
        monitor = {
            "left": capture["x"],
            "top": capture["y"],
            "width": capture["width"],
            "height": capture["height"],
        }

        image = self._grab_capture_image(monitor, ImageGrab, Image, mss)
        processed = self._prepare_image_for_ocr(
            image,
            ImageOps,
            self.config.get("ocr_profile", "uvchat"),
        )
        raw_text = pytesseract.image_to_string(
            processed,
            lang=self.config["ocr_lang"],
            config=f"--psm {self.config.get('ocr_psm', 6)}",
        )
        tabs_image, active_tab_name = self._capture_active_tab(
            ImageGrab, Image, ImageOps, mss, pytesseract, tabs_capture
        )
        cleaned_text = self._cleanup_ocr_text(raw_text)
        if not raw_text.strip():
            return "(no text detected)", "", image, processed, tabs_image, active_tab_name
        return cleaned_text, raw_text.strip(), image, processed, tabs_image, active_tab_name

    def _capture_active_tab(
        self,
        image_grab_module,
        image_module,
        image_ops_module,
        mss_module,
        pytesseract_module,
        tabs_capture=None,
    ):
        tabs_capture = tabs_capture or self.config.get("tabs_capture", {})
        if not tabs_capture or tabs_capture.get("width", 0) <= 0 or tabs_capture.get("height", 0) <= 0:
            return None, self.active_tab_name
        monitor = {
            "left": tabs_capture["x"],
            "top": tabs_capture["y"],
            "width": tabs_capture["width"],
            "height": tabs_capture["height"],
        }
        tabs_image = self._grab_capture_image(monitor, image_grab_module, image_module, mss_module)
        active_tab_name = self._extract_active_tab_name(
            tabs_image, image_module, image_ops_module, pytesseract_module
        )
        return tabs_image, active_tab_name

    def _grab_capture_image(self, monitor, image_grab_module, image_module, mss_module):
        backend = self.config.get("capture_backend", "auto").strip().lower() or "auto"
        if backend not in {"auto", "pil", "mss"}:
            backend = "auto"

        bbox = (
            monitor["left"],
            monitor["top"],
            monitor["left"] + monitor["width"],
            monitor["top"] + monitor["height"],
        )

        if backend == "pil":
            return self._grab_with_pil(image_grab_module, bbox)

        if backend == "mss":
            return self._grab_with_mss(mss_module, image_module, monitor)

        if os.name == "nt":
            try:
                pil_image = self._grab_with_pil(image_grab_module, bbox)
                if not self._is_mostly_black_image(pil_image):
                    return pil_image
            except Exception:
                pass

        mss_image = self._grab_with_mss(mss_module, image_module, monitor)
        if not self._is_mostly_black_image(mss_image):
            return mss_image

        if os.name == "nt":
            return self._grab_with_pil(image_grab_module, bbox)
        return mss_image

    @staticmethod
    def _grab_with_pil(image_grab_module, bbox):
        return image_grab_module.grab(bbox=bbox, all_screens=True)

    @staticmethod
    def _grab_with_mss(mss_module, image_module, monitor):
        with mss_module.mss() as sct:
            shot = sct.grab(monitor)
        return image_module.frombytes("RGB", shot.size, shot.rgb)

    @staticmethod
    def _is_mostly_black_image(image):
        grayscale = image.convert("L")
        histogram = grayscale.histogram()
        total_pixels = max(1, grayscale.width * grayscale.height)
        dark_pixels = sum(histogram[:12])
        average = sum(index * count for index, count in enumerate(histogram)) / total_pixels
        return dark_pixels / total_pixels > 0.92 and average < 10

    def _normalize_capture_coords(self, left, top, width, height):
        scale = self._get_display_scale()
        return (
            int(round(left * scale)),
            int(round(top * scale)),
            int(round(width * scale)),
            int(round(height * scale)),
        )

    def _get_display_scale(self):
        try:
            return self.root.winfo_fpixels("1i") / 96.0
        except tk.TclError:
            return 1.0

    @staticmethod
    def _prepare_image_for_ocr(image, image_ops_module, profile="uvchat"):
        from PIL import Image as PilImage

        profile = (profile or "uvchat").strip().lower()
        if profile == "uvchat":
            return UvChatApp._prepare_uvchat_image_for_ocr(
                image,
                image_ops_module,
                PilImage,
            )
        if profile == "uvchat_soft":
            return UvChatApp._prepare_uvchat_soft_image_for_ocr(
                image,
                image_ops_module,
                PilImage,
            )

        grayscale = image.convert("L")
        autocontrast = image_ops_module.autocontrast(grayscale)
        enlarged = autocontrast.resize(
            (autocontrast.width * 3, autocontrast.height * 3),
            resample=PilImage.Resampling.LANCZOS,
        )
        thresholded = enlarged.point(lambda px: 255 if px > 165 else 0, mode="1")
        return thresholded.convert("L")

    @staticmethod
    def _prepare_uvchat_image_for_ocr(image, image_ops_module, image_module):
        rgb = image.convert("RGB")
        width, height = rgb.size
        mask = image_module.new("L", (width, height), 0)

        for y in range(height):
            for x in range(width):
                red, green, blue = rgb.getpixel((x, y))
                brightness = red + green + blue
                is_white = red > 175 and green > 175 and blue > 175
                is_cyan = blue > 120 and green > 110 and blue > red + 25 and green > red + 15
                if brightness > 330 and (is_white or is_cyan):
                    mask.putpixel((x, y), 255)

        expanded = mask.resize(
            (mask.width * 4, mask.height * 4),
            resample=image_module.Resampling.NEAREST,
        )
        expanded = image_ops_module.autocontrast(expanded)
        return expanded.point(lambda px: 255 if px > 32 else 0, mode="1").convert("L")

    @staticmethod
    def _prepare_uvchat_soft_image_for_ocr(image, image_ops_module, image_module):
        rgb = image.convert("RGB")
        width, height = rgb.size
        mask = image_module.new("L", (width, height), 0)

        for y in range(height):
            for x in range(width):
                red, green, blue = rgb.getpixel((x, y))
                brightness = red + green + blue
                is_white = red > 145 and green > 145 and blue > 145
                is_cyan = blue > 95 and green > 90 and blue > red + 10 and green > red + 5
                if brightness > 260 and (is_white or is_cyan):
                    value = min(255, int((brightness - 220) * 1.6))
                    mask.putpixel((x, y), value)

        expanded = mask.resize(
            (mask.width * 3, mask.height * 3),
            resample=image_module.Resampling.LANCZOS,
        )
        expanded = image_ops_module.autocontrast(expanded)
        return expanded.point(lambda px: 255 if px > 70 else 0, mode="1").convert("L")

    @staticmethod
    def _prepare_tabs_image_for_ocr(image, image_ops_module, image_module):
        grayscale = image.convert("L")
        enlarged = grayscale.resize(
            (grayscale.width * 3, grayscale.height * 3),
            resample=image_module.Resampling.LANCZOS,
        )
        enlarged = image_ops_module.autocontrast(enlarged)
        return enlarged.point(lambda px: 255 if px > 135 else 0, mode="1").convert("L")

    @classmethod
    def _extract_active_tab_name(cls, tabs_image, image_module, image_ops_module, pytesseract_module):
        prepared = cls._prepare_tabs_image_for_ocr(tabs_image, image_ops_module, image_module)
        raw_tabs_text = pytesseract_module.image_to_string(
            prepared,
            lang="eng",
            config="--psm 7",
        )
        normalized = cls._normalize_tab_label(raw_tabs_text)
        return normalized or "LOCAL"

    @staticmethod
    def _normalize_tab_label(raw_tabs_text):
        normalized = re.sub(r"\s+", " ", raw_tabs_text or "").strip().upper()
        normalized = normalized.replace("LOCAI", "LOCAL")
        normalized = re.sub(r"[^A-Z0-9_ ]", "", normalized).strip()
        if not normalized:
            return ""
        if normalized.startswith("LOCAL"):
            return "LOCAL"
        return normalized[:24]

    @staticmethod
    def _find_tesseract_cmd(configured_path=""):
        if configured_path:
            candidate = Path(configured_path).expanduser()
            if candidate.exists():
                return str(candidate)
        command = shutil.which("tesseract")
        if command:
            return command
        local_tool = BASE_DIR / "tools" / "tesseract" / "tesseract.exe"
        if local_tool.exists():
            return str(local_tool)
        for path in WINDOWS_TESSERACT_PATHS:
            if path.exists():
                return str(path)
        return None

    @classmethod
    def _cleanup_ocr_text(cls, text):
        raw_lines = [line.rstrip() for line in text.splitlines()]
        cleaned_lines = []
        current_line = ""
        seen_chat_line = False

        for line in raw_lines:
            normalized = cls._normalize_ocr_line(line)
            if not normalized:
                continue
            if cls._is_ui_noise_line(normalized):
                continue

            if cls.CHAT_LINE_PATTERN.match(normalized):
                if current_line:
                    cleaned_lines.append(current_line)
                current_line = normalized
                seen_chat_line = True
                continue

            if current_line:
                current_line = f"{current_line} {normalized}".strip()
                continue

            if not seen_chat_line and len(normalized) >= 12:
                cleaned_lines.append(normalized)

        if current_line:
            cleaned_lines.append(current_line)

        deduped = []
        for line in cleaned_lines:
            if not deduped or deduped[-1] != line:
                deduped.append(line)

        if seen_chat_line:
            deduped = [line for line in deduped if cls.CHAT_LINE_PATTERN.match(line)]
        return "\n".join(deduped).strip()

    @staticmethod
    def _normalize_ocr_line(line):
        line = line.replace("|", "I")
        line = line.replace("’", "'")
        line = re.sub(r"\s+", " ", line).strip()
        line = re.sub(r"^\.+", "", line).strip()
        line = re.sub(r"^[=_\-]+", "", line).strip()
        line = re.sub(r"[=_\-]+$", "", line).strip()
        line = re.sub(r"\b([A-Za-z])=(\w)", r"\1\2", line)
        line = re.sub(r"\b([A-Za-z])1([a-z]{2,})\b", r"\1l\2", line)
        line = re.sub(r"\b1([a-z]{2,})\b", r"l\1", line)
        line = re.sub(r"\b([a-z]{2,})vv([a-z]{2,})\b", r"\1w\2", line, flags=re.IGNORECASE)
        line = re.sub(r"\bV([a-z]{2,})\b", lambda match: "W" + match.group(1), line)
        return line

    @classmethod
    def _is_ui_noise_line(cls, line):
        lower = line.lower()
        if "(info)" in lower or "[info]" in lower:
            return True
        if cls.TIMESTAMP_PATTERN.match(line) and " is now online" in lower:
            return True
        if cls.TIMESTAMP_PATTERN.match(line) and " is now offline" in lower:
            return True
        if lower in {"local", "zackbar", "chat", "pm", "friends"}:
            return True
        if lower == "utherverse transport" or lower == "transport":
            return True
        if lower.startswith("local ") and len(line) < 24:
            return True
        if "is now online" in lower or "is now offline" in lower:
            return True
        if lower.startswith("(info):") or lower.startswith("(info) "):
            return True
        if "your friend [" in lower:
            return True
        if lower.startswith("fps") or lower.startswith("latency") or lower.startswith("server"):
            return True
        if lower.startswith("domain") or lower.startswith("region") or lower.startswith("online"):
            return True
        if lower.startswith("template") or lower.startswith("instance"):
            return True
        if len(line) < 4:
            return True
        alpha_count = sum(char.isalpha() for char in line)
        if alpha_count and alpha_count < 3 and len(line) < 10:
            return True
        return False

    def _extract_new_chat_lines(self, text, tab_name="LOCAL"):
        if (
            not text
            or text == "(no text detected)"
            or text.startswith("Missing dependency")
            or text.startswith("Tesseract OCR")
        ):
            return []

        tab_state = self.chat_histories.setdefault(
            tab_name or "LOCAL",
            {"original": [], "translated": [], "seen": set()},
        )
        seen_lines = tab_state["seen"]
        new_lines = []
        for line in text.splitlines():
            normalized = line.strip()
            if not normalized or not self.CHAT_LINE_PATTERN.match(normalized):
                continue
            lower = normalized.lower()
            if "(info)" in lower or "[info]" in lower:
                continue
            if " is now online" in lower or " is now offline" in lower:
                continue
            if "your friend [" in lower:
                continue
            if normalized in seen_lines:
                continue
            seen_lines.add(normalized)
            new_lines.append(normalized)
        return new_lines

    def _translate_text(self, text):
        mode = self.config["translation"]["mode"]
        if mode == "echo" or not text or text.startswith("Missing dependency") or text.startswith("Tesseract OCR"):
            return text

        if mode == "libretranslate":
            try:
                import requests
            except ImportError:
                return "requests is missing. Install Python dependencies first."

            payload = {
                "q": text,
                "source": self.config["source_language"],
                "target": self.config["target_language"],
                "format": "text",
            }
            api_key = self.config["translation"].get("api_key", "").strip()
            headers = {}
            if api_key:
                headers["X-API-Key"] = api_key

            try:
                response = requests.post(
                    self.config["translation"]["libretranslate_url"],
                    json=payload,
                    headers=headers,
                    timeout=20,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("translatedText", text)
            except Exception as exc:
                return f"Translation error: {exc}"

        if mode == "google":
            try:
                import requests
            except ImportError:
                return "requests is missing. Install Python dependencies first."

            api_key = self.config["translation"].get("google_api_key", "").strip()
            if not api_key:
                return "Translation error: missing Google API key."

            payload = {
                "q": text,
                "target": self.config["target_language"],
                "format": "text",
            }
            source_language = self.config["source_language"].strip()
            if source_language and source_language != "auto":
                payload["source"] = source_language

            try:
                response = requests.post(
                    "https://translation.googleapis.com/language/translate/v2",
                    params={"key": api_key},
                    json=payload,
                    timeout=20,
                )
                response.raise_for_status()
                data = response.json()
                translations = data.get("data", {}).get("translations", [])
                if not translations:
                    return text
                return "\n".join(
                    item.get("translatedText", "") for item in translations if item.get("translatedText")
                ) or text
            except Exception as exc:
                return f"Translation error: {exc}"

        if mode == "oci":
            try:
                import oci
            except ImportError:
                return "Translation error: install the oci Python package in the venv."

            config_file = (
                self.config["translation"].get("oci_config_file", "").strip()
                or str(Path.home() / ".oci" / "config")
            )
            profile = self.config["translation"].get("oci_profile", "").strip() or "DEFAULT"
            compartment_id = self.config["translation"].get("oci_compartment_id", "").strip()
            if not compartment_id:
                return "Translation error: missing OCI compartment OCID."

            try:
                oci_config = oci.config.from_file(config_file, profile)
                client = oci.ai_language.AIServiceLanguageClient(oci_config)
                models = oci.ai_language.models
                source_language = self.config["source_language"].strip()
                if source_language and source_language != "auto":
                    detected_language = source_language.lower()
                else:
                    detect_response = client.batch_detect_dominant_language(
                        models.BatchDetectDominantLanguageDetails(
                            compartment_id=compartment_id,
                            documents=[models.DominantLanguageDocument(key="detect", text=text)],
                        )
                    )
                    detect_docs = getattr(detect_response.data, "documents", None) or []
                    detected_languages = (
                        getattr(detect_docs[0], "languages", None) if detect_docs else None
                    ) or []
                    detected_language = (
                        getattr(detected_languages[0], "code", "") if detected_languages else ""
                    ).lower()
                if not detected_language:
                    return "Translation error: OCI could not detect source language."

                translation_response = client.batch_language_translation(
                    models.BatchLanguageTranslationDetails(
                        compartment_id=compartment_id,
                        documents=[
                            models.TextDocument(
                                key="uvchat",
                                text=text,
                                language_code=detected_language,
                            )
                        ],
                        target_language_code=self.config["target_language"].strip() or "de",
                    )
                )
                documents = getattr(translation_response.data, "documents", None) or []
                if not documents:
                    return text
                return getattr(documents[0], "translated_text", "") or text
            except Exception as exc:
                return f"Translation error: {exc}"

        return text

    def _update_texts(
        self,
        new_original_lines,
        translated,
        raw_text="",
        preview_image=None,
        processed_image=None,
        tabs_image=None,
        active_tab_name="LOCAL",
    ):
        self.last_capture_image = preview_image.copy() if preview_image is not None else None
        self.last_processed_image = (
            processed_image.copy() if processed_image is not None else None
        )
        self.last_tabs_capture_image = tabs_image.copy() if tabs_image is not None else None
        self.active_tab_name = active_tab_name or "LOCAL"
        self.active_tab_var.set(f"Active tab: {self.active_tab_name}")
        tab_state = self.chat_histories.setdefault(
            self.active_tab_name,
            {"original": [], "translated": [], "seen": set()},
        )
        self.original_history_lines = tab_state["original"]
        self.translated_history_lines = tab_state["translated"]
        self.seen_chat_lines = tab_state["seen"]
        self._set_preview_images(preview_image, processed_image, tabs_image)
        if new_original_lines:
            self.original_history_lines.extend(new_original_lines)
            self._append_history_lines(
                self.translated_history_lines,
                translated.splitlines() if translated else new_original_lines,
            )
            self._set_scrolled_text(
                self.original_text,
                "\n".join(self.original_history_lines),
            )
            self._set_scrolled_text(
                self.translated_text,
                "\n".join(self.translated_history_lines),
            )
            self._set_status(f"Added {len(new_original_lines)} new chat line(s).")
        elif preview_image is not None:
            fallback_text = raw_text or "(no text detected)"
            if self.original_history_lines:
                self._set_scrolled_text(
                    self.original_text,
                    "\n".join(self.original_history_lines),
                )
            else:
                self._set_scrolled_text(self.original_text, fallback_text)
            self._set_scrolled_text(
                self.translated_text,
                "\n".join(self.translated_history_lines),
            )
            self._set_status("No new chat lines matched yet. Original OCR updated only.")

    def _set_preview_images(self, raw_image, processed_image, tabs_image=None):
        from PIL import ImageTk

        if raw_image is None:
            self.capture_preview_label.configure(text="No capture yet.")
            self.capture_preview_image = None
            self.processed_preview_image = None
            self.tabs_preview_image = None
            self.capture_preview_image_label.configure(image="", text="No raw capture yet.")
            self.processed_preview_image_label.configure(image="", text="No OCR preview yet.")
            self.tabs_preview_image_label.configure(image="", text="No tabs preview yet.")
            return

        self.capture_preview_label.configure(
            text=f"Preview updated: raw {raw_image.width}x{raw_image.height}",
        )

        raw_preview = raw_image.copy()
        raw_preview.thumbnail((440, 180))
        self.capture_preview_image = ImageTk.PhotoImage(raw_preview)
        self.capture_preview_image_label.configure(
            image=self.capture_preview_image,
            text="",
        )

        if processed_image is None:
            self.processed_preview_image = None
            self.processed_preview_image_label.configure(image="", text="No OCR preview yet.")
            return

        processed_preview = processed_image.copy().convert("RGB")
        processed_preview.thumbnail((440, 180))
        self.processed_preview_image = ImageTk.PhotoImage(processed_preview)
        self.processed_preview_image_label.configure(
            image=self.processed_preview_image,
            text="",
        )

        if tabs_image is None:
            self.tabs_preview_image = None
            self.tabs_preview_image_label.configure(image="", text="No tabs preview yet.")
            return

        tabs_preview = tabs_image.copy()
        tabs_preview.thumbnail((440, 64))
        self.tabs_preview_image = ImageTk.PhotoImage(tabs_preview)
        self.tabs_preview_image_label.configure(
            image=self.tabs_preview_image,
            text="",
        )

    @staticmethod
    def _set_scrolled_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.see(tk.END)
        widget.configure(state="disabled")

    @staticmethod
    def _append_history_lines(history, lines):
        for line in lines:
            normalized = line.strip()
            if normalized:
                history.append(normalized)


def enable_dpi_awareness():
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass
    app = UvChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

