#!/usr/bin/env python3
import json
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
CONFIG_EXAMPLE_PATH = BASE_DIR / "config.example.json"


DEFAULT_CONFIG = {
    "capture": {"x": 0, "y": 0, "width": 600, "height": 300},
    "poll_interval_ms": 1500,
    "ocr_lang": "eng",
    "source_language": "auto",
    "target_language": "de",
    "translation": {
        "mode": "echo",
        "libretranslate_url": "http://127.0.0.1:5000/translate",
        "api_key": "",
    },
    "window": {"always_on_top": True, "width": 920, "height": 760},
}


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
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.is_running = False
        self.is_busy = False
        self.last_ocr_text = ""
        self.last_translated_text = ""

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
        for i in range(9):
            top.columnconfigure(i, weight=1)

        self.x_var = tk.StringVar()
        self.y_var = tk.StringVar()
        self.w_var = tk.StringVar()
        self.h_var = tk.StringVar()
        self.poll_var = tk.StringVar()
        self.ocr_lang_var = tk.StringVar()
        self.source_lang_var = tk.StringVar()
        self.target_lang_var = tk.StringVar()
        self.topmost_var = tk.BooleanVar()
        self.translation_mode_var = tk.StringVar()
        self.libre_url_var = tk.StringVar()
        self.libre_api_key_var = tk.StringVar()

        fields = [
            ("X", self.x_var),
            ("Y", self.y_var),
            ("Width", self.w_var),
            ("Height", self.h_var),
            ("Poll ms", self.poll_var),
            ("OCR", self.ocr_lang_var),
            ("Source", self.source_lang_var),
            ("Target", self.target_lang_var),
        ]

        for index, (label, variable) in enumerate(fields):
            ttk.Label(top, text=label).grid(row=0, column=index, sticky="w", padx=4)
            ttk.Entry(top, textvariable=variable, width=10).grid(
                row=1, column=index, sticky="ew", padx=4, pady=(2, 8)
            )

        ttk.Label(top, text="Mode").grid(row=2, column=0, sticky="w", padx=4)
        ttk.Combobox(
            top,
            textvariable=self.translation_mode_var,
            values=["echo", "libretranslate"],
            state="readonly",
            width=16,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=4)

        ttk.Label(top, text="LibreTranslate URL").grid(
            row=2, column=2, columnspan=3, sticky="w", padx=4
        )
        ttk.Entry(top, textvariable=self.libre_url_var).grid(
            row=3, column=2, columnspan=4, sticky="ew", padx=4
        )

        ttk.Label(top, text="API Key").grid(row=2, column=6, sticky="w", padx=4)
        ttk.Entry(top, textvariable=self.libre_api_key_var, show="*").grid(
            row=3, column=6, sticky="ew", padx=4
        )

        ttk.Checkbutton(
            top,
            text="Always On Top",
            variable=self.topmost_var,
            command=self._toggle_topmost,
        ).grid(row=2, column=7, sticky="w", padx=4)

        buttons = ttk.Frame(top)
        buttons.grid(row=3, column=7, columnspan=2, sticky="e", padx=4)
        ttk.Button(buttons, text="Save", command=self.save_current_config).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(buttons, text="Start", command=self.start_scan).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(buttons, text="Stop", command=self.stop_scan).pack(side="left")

        status_frame = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        status_frame.grid(row=1, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar()
        ttk.Label(
            status_frame, textvariable=self.status_var, foreground="#c98200"
        ).grid(row=0, column=0, sticky="w")

        panes = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        panes.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))

        original_frame = ttk.LabelFrame(panes, text="Original OCR")
        translated_frame = ttk.LabelFrame(panes, text="Translated")

        self.original_text = ScrolledText(
            original_frame, wrap="word", font=("TkDefaultFont", 11)
        )
        self.original_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.translated_text = ScrolledText(
            translated_frame, wrap="word", font=("TkDefaultFont", 11)
        )
        self.translated_text.pack(fill="both", expand=True, padx=8, pady=8)

        panes.add(original_frame, weight=1)
        panes.add(translated_frame, weight=1)

        help_frame = ttk.LabelFrame(self.root, text="Usage", padding=12)
        help_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        help_text = (
            "1. Put the Utherverse chat on screen.\n"
            "2. Enter the chat region coordinates.\n"
            "3. Start scanning.\n"
            "4. Use 'echo' first. Switch to LibreTranslate later if needed.\n"
            "5. If OCR stays empty, increase chat contrast or font size."
        )
        ttk.Label(help_frame, text=help_text, justify="left").pack(anchor="w")

    def _apply_config_to_ui(self):
        capture = self.config["capture"]
        self.x_var.set(str(capture["x"]))
        self.y_var.set(str(capture["y"]))
        self.w_var.set(str(capture["width"]))
        self.h_var.set(str(capture["height"]))
        self.poll_var.set(str(self.config["poll_interval_ms"]))
        self.ocr_lang_var.set(self.config["ocr_lang"])
        self.source_lang_var.set(self.config["source_language"])
        self.target_lang_var.set(self.config["target_language"])
        self.topmost_var.set(self.config["window"]["always_on_top"])
        self.translation_mode_var.set(self.config["translation"]["mode"])
        self.libre_url_var.set(self.config["translation"]["libretranslate_url"])
        self.libre_api_key_var.set(self.config["translation"].get("api_key", ""))

    def _read_ui_into_config(self):
        self.config["capture"] = {
            "x": int(self.x_var.get() or "0"),
            "y": int(self.y_var.get() or "0"),
            "width": int(self.w_var.get() or "0"),
            "height": int(self.h_var.get() or "0"),
        }
        self.config["poll_interval_ms"] = int(self.poll_var.get() or "1500")
        self.config["ocr_lang"] = self.ocr_lang_var.get().strip() or "eng"
        self.config["source_language"] = self.source_lang_var.get().strip() or "auto"
        self.config["target_language"] = self.target_lang_var.get().strip() or "de"
        self.config["translation"]["mode"] = self.translation_mode_var.get().strip() or "echo"
        self.config["translation"]["libretranslate_url"] = self.libre_url_var.get().strip()
        self.config["translation"]["api_key"] = self.libre_api_key_var.get().strip()
        self.config["window"]["always_on_top"] = bool(self.topmost_var.get())

    def save_current_config(self):
        try:
            self._read_ui_into_config()
            save_config(self.config)
            self._set_status(f"Saved config to {CONFIG_PATH}")
        except Exception as exc:
            self._set_status(f"Could not save config: {exc}")

    def _toggle_topmost(self):
        self.root.attributes("-topmost", self.topmost_var.get())

    def _set_status(self, message):
        self.status_var.set(message)

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
        self._set_status("Scanning started.")
        self.root.after(100, self._scan_tick)

    def stop_scan(self):
        self.is_running = False
        self._set_status("Scanning stopped.")

    def _scan_tick(self):
        if not self.is_running:
            return
        if not self.is_busy:
            self.is_busy = True
            threading.Thread(target=self._run_capture_cycle, daemon=True).start()
        self.root.after(self.config["poll_interval_ms"], self._scan_tick)

    def _run_capture_cycle(self):
        try:
            ocr_text = self._capture_and_ocr()
            translated = self._translate_text(ocr_text)
            self.root.after(0, lambda: self._update_texts(ocr_text, translated))
        except Exception as exc:
            self.root.after(0, lambda: self._set_status(f"Scan error: {exc}"))
        finally:
            self.is_busy = False

    def _capture_and_ocr(self):
        try:
            import mss
            from PIL import Image
            import pytesseract
        except ImportError as exc:
            missing = getattr(exc, "name", str(exc))
            return (
                "Missing dependency.\n\n"
                f"Could not import: {missing}\n"
                "Install packages from requirements.txt plus system OCR packages.\n"
                "Recommended: python3-tk, tesseract-ocr, pillow, mss, pytesseract."
            )

        if shutil.which("tesseract") is None:
            return (
                "Tesseract OCR is not installed.\n\n"
                "Install the system package 'tesseract-ocr' and try again."
            )

        capture = self.config["capture"]
        monitor = {
            "left": capture["x"],
            "top": capture["y"],
            "width": capture["width"],
            "height": capture["height"],
        }

        with mss.mss() as sct:
            shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        text = pytesseract.image_to_string(image, lang=self.config["ocr_lang"])
        text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
        if not text:
            return "(no text detected)"
        return text

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

            response = requests.post(
                self.config["translation"]["libretranslate_url"],
                json=payload,
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("translatedText", text)

        return text

    def _update_texts(self, original, translated):
        self._set_scrolled_text(self.original_text, original)
        self._set_scrolled_text(self.translated_text, translated)
        if original != self.last_ocr_text or translated != self.last_translated_text:
            self._set_status("Updated chat text.")
        self.last_ocr_text = original
        self.last_translated_text = translated

    @staticmethod
    def _set_scrolled_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state="disabled")


def main():
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
