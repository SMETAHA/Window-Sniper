# window_sniper.py — Window Sniper v1.1 (RU/EN + Dark/Light + true click-block + Apply button + mode cooldowns)
# Windows-only. Requires: PySide6
#
# Hotkey:
#   Ctrl+Alt+S  -> Toggle Sniper Mode (RegisterHotKey)
#
# In Sniper Mode:
#   LMB    -> Copy info (blocked: won't click apps)
#   RMB    -> Exit Sniper Mode
#   ESC    -> Exit Sniper Mode
#   SPACE  -> Pin/Unpin
#   M      -> Cycle copy format (Text/Markdown/JSON) [with cooldown]
#   TAB    -> Toggle Compact/Expanded view           [with cooldown]
#
# Notes:
# - NO low-level hooks: input is captured by a fullscreen blocker (no admin).
# - Blocker is NOT fully transparent (draws alpha=1) so clicks cannot pass through.
# - Additional keyboard polling fallback stays (helps when focus is weird).

from __future__ import annotations
from datetime import date

import os
import sys
import time
import json
import ctypes
import logging
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, asdict
from ctypes import wintypes
from typing import Optional, Tuple, Callable

if os.name != "nt":
    print("This script is Windows-only.")
    sys.exit(1)

# --- ctypes.wintypes compatibility ---
if not hasattr(wintypes, "ULONG_PTR"):
    wintypes.ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QAbstractNativeEventFilter, QRect, QLocale
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QPen, QFont, QAction,
    QCursor, QGuiApplication, QFontMetrics, QLinearGradient, QColor
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QComboBox, QSlider, QPushButton,
    QMessageBox, QFrame, QSizePolicy
)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

APP_USER_MODEL_ID = "com.window_sniper.app"  # любое стабильное, главное неизменное

def set_appusermodel_id(appid: str) -> None:
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(appid))
    except Exception:
        pass


# ----------------------------
# DPI awareness
# ----------------------------
try:
    DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
    user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

# ----------------------------
# WinAPI constants
# ----------------------------
WM_HOTKEY = 0x0312

HOTKEY_MODS = 0x0002 | 0x0001  # MOD_CONTROL | MOD_ALT
HOTKEY_VK = 0x53               # 'S'
HOTKEY_ID = 0xBEEF

VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_TAB = 0x09
VK_M = 0x4D
VK_RBUTTON = 0x02

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GA_ROOT = 2

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

GW_HWNDNEXT = 2

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020

# SetWindowPos
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

# Composition
ACCENT_DISABLED = 0
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
WCA_ACCENT_POLICY = 19

APP_VERSION = "1.1"
COPY_FORMAT_KEYS = ["fmt_text", "fmt_markdown", "fmt_json"]
AUTHOR_NAME = "Ник"              # <- впиши как хочешь
AUTHOR_TAG = "@cmetana"          # <- опционально (или убери строку)
LICENSE_NAME = "MIT"             # <- для вида (можешь поменять на Apache-2.0 / GPL-3.0 / Proprietary)
BUILD_DATE = "2025-11-28"
COPYRIGHT = f"© {date.today().year} {AUTHOR_NAME}"


# ----------------------------
# Paths + logging
# ----------------------------
def app_data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "WindowSniper")
    os.makedirs(path, exist_ok=True)
    return path

LOG_PATH = os.path.join(app_data_dir(), "sniper.log")
CFG_PATH = os.path.join(app_data_dir(), "config.json")

logger = logging.getLogger("window_sniper")
logger.setLevel(logging.INFO)
_handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.addHandler(_handler)

def _excepthook(exc_type, exc, tb):
    logger.exception("Unhandled exception", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)

sys.excepthook = _excepthook
set_appusermodel_id(APP_USER_MODEL_ID)


# ----------------------------
# i18n
# ----------------------------
def system_lang() -> str:
    name = QLocale.system().name().lower()
    return "ru" if name.startswith("ru") else "en"

I18N = {
    "en": {
        "app_name": "Window Sniper",
        "tray_toggle": "Sniper Mode (Ctrl+Alt+S)",
        "tray_copy": "Copy now",
        "tray_pin": "Pin/Unpin",
        "tray_view": "Toggle view",
        "tray_settings": "Settings…",
        "tray_about": "About",
        "tray_exit": "Exit",
        "tray_copy_format": "Copy format",

        "mode_title": "Window Sniper",
        "mode_on": "Sniper Mode ON",
        "mode_off": "Sniper Mode OFF",

        "status_hint_blocked": "LMB copy | RMB/ESC exit | Space pin | M format | Tab view",
        "status_pinned": "PINNED",
        "status_unpinned": "UNPINNED",
        "status_view": "View: {v}",
        "status_format": "Format: {f}",
        "status_settings_applied": "Settings applied",
        "status_copied": "COPIED ✅",
        "hotkey_fail": "Hotkey registration failed (Ctrl+Alt+S). It may be used by another app.",

        "view_compact": "compact",
        "view_expanded": "expanded",

        "fmt_text": "Text",
        "fmt_markdown": "Markdown",
        "fmt_json": "JSON",

        "settings_title": "Window Sniper — Settings",
        "sec_behavior": "Behavior",
        "sec_visual": "Visual",
        "sec_language": "Language",

        "opt_block_clicks": "Block clicks in Sniper Mode (recommended)",
        "opt_show_outline": "Show outline highlight",
        "opt_auto_exit": "Auto-exit after copy",

        "opt_blur": "Blur",
        "blur_auto": "Auto",
        "blur_on": "On",
        "blur_off": "Off",

        "opt_theme": "Theme",
        "theme_dark": "Dark",
        "theme_light": "Light",

        "opt_default_view": "Default view",
        "opt_copy_format": "Copy format",
        "opt_scale": "Overlay scale",
        "opt_language": "Interface language",

        "lang_auto": "Auto",
        "lang_en": "English",
        "lang_ru": "Russian",

        "btn_save": "Save",
        "btn_apply": "Apply",
        "btn_cancel": "Cancel",

        "about_title": "About Window Sniper",
"about_body": (
    "Window Sniper — window inspector under cursor.\n\n"
    "Version: {ver}\n"
    "Author: {author} {tag}\n"
    "Build date: {build}\n"
    "{copyright}\n"
    "License: {license}\n\n"
    "Hotkeys (Sniper Mode):\n"
    "• LMB — copy\n"
    "• RMB / Esc — exit\n"
    "• Space — pin/unpin\n"
    "• M — copy format\n"
    "• Tab — view (compact/expanded)\n\n"
    "Config: {cfg}\n"
    "Log: {log}"
),

    },
    "ru": {
        "app_name": "Window Sniper",
        "tray_toggle": "Режим снайпера (Ctrl+Alt+S)",
        "tray_copy": "Скопировать сейчас",
        "tray_pin": "Закрепить/открепить",
        "tray_view": "Переключить вид",
        "tray_settings": "Настройки…",
        "tray_about": "О программе",
        "tray_exit": "Выход",
        "tray_copy_format": "Формат копирования",

        "mode_title": "Window Sniper",
        "mode_on": "Режим снайпера ВКЛ",
        "mode_off": "Режим снайпера ВЫКЛ",

        "status_hint_blocked": "ЛКМ копировать | ПКМ/Esc выход | Space закреп | M формат | Tab вид",
        "status_pinned": "ЗАКРЕПЛЕНО",
        "status_unpinned": "ОТКРЕПЛЕНО",
        "status_view": "Вид: {v}",
        "status_format": "Формат: {f}",
        "status_settings_applied": "Настройки применены",
        "status_copied": "СКОПИРОВАНО ✅",
        "hotkey_fail": "Не удалось зарегистрировать хоткей (Ctrl+Alt+S). Возможно, он занят другой программой.",

        "view_compact": "компактный",
        "view_expanded": "расширенный",

        "fmt_text": "Текст",
        "fmt_markdown": "Markdown",
        "fmt_json": "JSON",

        "settings_title": "Window Sniper — Настройки",
        "sec_behavior": "Поведение",
        "sec_visual": "Внешний вид",
        "sec_language": "Язык",

        "opt_block_clicks": "Блокировать клики в режиме снайпера (рекомендуется)",
        "opt_show_outline": "Подсветка рамкой вокруг окна",
        "opt_auto_exit": "Автовыход после копирования",

        "opt_blur": "Размытие",
        "blur_auto": "Авто",
        "blur_on": "Вкл",
        "blur_off": "Выкл",

        "opt_theme": "Тема",
        "theme_dark": "Тёмная",
        "theme_light": "Светлая",

        "opt_default_view": "Вид по умолчанию",
        "opt_copy_format": "Формат копирования",
        "opt_scale": "Масштаб оверлея",
        "opt_language": "Язык интерфейса",

        "lang_auto": "Авто",
        "lang_en": "Английский",
        "lang_ru": "Русский",

        "btn_save": "Сохранить",
        "btn_apply": "Применить",
        "btn_cancel": "Отмена",

        "about_title": "О Window Sniper",
"about_body": (
    "Window Sniper — инспектор окна под курсором.\n\n"
    "Версия: {ver}\n"
    "Автор: {author} {tag}\n"
    "Дата сборки: {build}\n"
    "{copyright}\n"
    "Лицензия: {license}\n\n"
    "Горячие клавиши (в режиме снайпера):\n"
    "• ЛКМ — копировать\n"
    "• ПКМ / Esc — выйти\n"
    "• Space — закрепить/открепить\n"
    "• M — формат копирования\n"
    "• Tab — вид (компакт/расшир)\n\n"
    "Конфиг: {cfg}\n"
    "Лог: {log}"
),

    },
}

def tr(lang: str, key: str, **kwargs) -> str:
    pack = I18N.get(lang) or I18N["en"]
    s = pack.get(key) or I18N["en"].get(key) or key
    try:
        return s.format(**kwargs)
    except Exception:
        return s

def resolve_lang(cfg_lang: str) -> str:
    if cfg_lang == "auto":
        return system_lang()
    return cfg_lang if cfg_lang in ("ru", "en") else "en"

# ----------------------------
# Config
# ----------------------------
@dataclass
class SniperConfig:
    overlay_offset_x: int = 18
    overlay_offset_y: int = 18
    update_ms: int = 33
    keyboard_poll_ms: int = 12

    block_clicks: bool = True
    auto_exit_after_copy: bool = False
    show_outline: bool = True

    blur_mode: str = "auto"         # auto/on/off
    theme: str = "dark"             # dark/light
    language: str = "auto"          # auto/en/ru

    default_view: str = "compact"   # compact/expanded
    overlay_scale_percent: int = 100  # 80..160
    copy_format_idx: int = 0        # 0..2

    # Requested: delay on switching copy/view modes
    switch_cooldown_ms: int = 220   # cooldown for "M" and "Tab"

def load_config() -> SniperConfig:
    try:
        if os.path.exists(CFG_PATH):
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cfg = SniperConfig(**raw)

            if cfg.blur_mode not in ("auto", "on", "off"):
                cfg.blur_mode = "auto"
            if cfg.theme not in ("dark", "light"):
                cfg.theme = "dark"
            if cfg.language not in ("auto", "en", "ru"):
                cfg.language = "auto"
            if cfg.default_view not in ("compact", "expanded"):
                cfg.default_view = "compact"

            cfg.overlay_scale_percent = int(max(80, min(160, cfg.overlay_scale_percent)))
            cfg.copy_format_idx = int(max(0, min(2, cfg.copy_format_idx)))
            cfg.update_ms = int(max(10, min(200, cfg.update_ms)))
            cfg.keyboard_poll_ms = int(max(8, min(50, cfg.keyboard_poll_ms)))
            cfg.switch_cooldown_ms = int(max(80, min(1000, cfg.switch_cooldown_ms)))
            return cfg
    except Exception:
        logger.exception("Failed to load config")
    return SniperConfig()

def save_config(cfg: SniperConfig) -> None:
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(cfg), f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save config")

# ----------------------------
# WinAPI structs
# ----------------------------
class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint32),  # AABBGGRR
        ("AnimationId", ctypes.c_int),
    ]

class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]

# ----------------------------
# Hotkey filter
# ----------------------------
class WinHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, on_hotkey):
        super().__init__()
        self.hotkey_id = hotkey_id
        self.on_hotkey = on_hotkey

    def nativeEventFilter(self, eventType, message):
        if eventType not in ("windows_generic_MSG", "windows_dispatcher_MSG",
                             b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message == WM_HOTKEY and int(msg.wParam) == int(self.hotkey_id):
            try:
                self.on_hotkey()
            except Exception:
                logger.exception("Hotkey handler failed")
            return True, 0
        return False, 0

# ----------------------------
# Win helpers
# ----------------------------
def is_key_down(vk: int) -> bool:
    return (user32.GetAsyncKeyState(vk) & 0x8000) != 0

def get_virtual_screen_rect() -> Tuple[int, int, int, int]:
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return vx, vy, vw, vh

def get_cursor_pos() -> Tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    r = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return (r.left, r.top, r.right, r.bottom)

def get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value

def get_window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value

def get_window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)

def is_window_visible(hwnd: int) -> bool:
    return bool(user32.IsWindowVisible(hwnd))

def is_window_minimized(hwnd: int) -> bool:
    try:
        return bool(user32.IsIconic(hwnd))
    except Exception:
        return False

def get_process_image_path(pid: int) -> Optional[str]:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        size = wintypes.DWORD(4096)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(h)

def clamp_overlay_pos(x: int, y: int, w: int, h: int) -> Tuple[int, int]:
    vx, vy, vw, vh = get_virtual_screen_rect()
    if x + w > vx + vw:
        x = (vx + vw) - w - 8
    if y + h > vy + vh:
        y = (vy + vh) - h - 8
    if x < vx:
        x = vx + 8
    if y < vy:
        y = vy + 8
    return x, y

def point_in_rect(x: int, y: int, rect: Tuple[int, int, int, int]) -> bool:
    l, t, r, b = rect
    return (l <= x < r) and (t <= y < b)

def get_hwnd_under_cursor_scan_zorder(x: int, y: int, ignore_pid: int) -> int:
    hwnd = user32.GetTopWindow(None)
    while hwnd:
        try:
            if is_window_visible(hwnd) and not is_window_minimized(hwnd):
                pid = get_window_pid(hwnd)
                if pid != ignore_pid:
                    rect = get_window_rect(hwnd)
                    if rect and point_in_rect(x, y, rect):
                        root = user32.GetAncestor(hwnd, GA_ROOT)
                        return root or hwnd
        except Exception:
            pass
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
    return 0

# ----------------------------
# Data
# ----------------------------
@dataclass
class WindowInfo:
    hwnd: int
    title: str
    cls: str
    pid: int
    exe: Optional[str]
    left: int
    top: int
    width: int
    height: int

def collect_window_info(hwnd: int) -> Optional[WindowInfo]:
    if not hwnd:
        return None
    rect = get_window_rect(hwnd)
    if not rect:
        return None
    left, top, right, bottom = rect

    pid = get_window_pid(hwnd)
    title = get_window_title(hwnd).strip() or "(no title)"
    cls = get_window_class(hwnd).strip() or "(no class)"

    exe = None
    try:
        exe = get_process_image_path(pid)
    except Exception:
        exe = None

    return WindowInfo(
        hwnd=int(hwnd),
        title=title,
        cls=cls,
        pid=pid,
        exe=exe,
        left=int(left),
        top=int(top),
        width=int(right - left),
        height=int(bottom - top),
    )

# ----------------------------
# Blur / composition
# ----------------------------
def theme_accent_color(theme: str) -> int:
    return 0xCCF8F8F8 if theme == "light" else 0xCC202020  # AABBGGRR

def set_accent(hwnd: int, accent_state: int, color_aabbggrr: int) -> bool:
    try:
        set_comp = user32.SetWindowCompositionAttribute
    except Exception:
        return False
    try:
        accent = ACCENT_POLICY()
        accent.AccentState = accent_state
        accent.AccentFlags = 2
        accent.GradientColor = color_aabbggrr
        accent.AnimationId = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        ok = set_comp(hwnd, ctypes.byref(data))
        return bool(ok)
    except Exception:
        return False

def apply_blur_mode(hwnd: int, mode: str, theme: str) -> bool:
    color = theme_accent_color(theme)
    if mode == "off":
        return set_accent(hwnd, ACCENT_DISABLED, color)
    if mode in ("auto", "on"):
        return set_accent(hwnd, ACCENT_ENABLE_ACRYLICBLURBEHIND, color) or set_accent(hwnd, ACCENT_ENABLE_BLURBEHIND, color)
    return False

def clear_ws_ex_transparent(hwnd: int):
    try:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex & WS_EX_TRANSPARENT:
            ex &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
    except Exception:
        pass

def enforce_topmost(hwnd: int):
    try:
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    except Exception:
        pass

def set_click_through(hwnd: int, enabled: bool):
    # Only used for overlay/outline.
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enabled:
        ex |= WS_EX_TRANSPARENT
    else:
        ex &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)

# ----------------------------
# Formatting
# ----------------------------
def format_info_for_clipboard(info: WindowInfo, fmt_idx: int) -> str:
    exe_name = os.path.basename(info.exe) if info.exe else "N/A"
    exe_path = info.exe if info.exe else "N/A"
    hwnd_hex = f"0x{info.hwnd:08X}"

    if fmt_idx == 1:
        return "\n".join([
            "### Window Sniper",
            f"- **Title:** {info.title}",
            f"- **Process:** {exe_name}",
            f"- **PID:** {info.pid}",
            f"- **HWND:** `{hwnd_hex}`",
            f"- **Size:** {info.width}×{info.height}",
            f"- **Pos:** {info.left}, {info.top}",
            f"- **Class:** `{info.cls}`",
            f"- **Path:** `{exe_path}`",
        ])
    if fmt_idx == 2:
        data = {
            "title": info.title,
            "process": exe_name if exe_name != "N/A" else None,
            "pid": info.pid,
            "hwnd": info.hwnd,
            "hwnd_hex": hwnd_hex,
            "class": info.cls,
            "size": {"w": info.width, "h": info.height},
            "pos": {"x": info.left, "y": info.top},
            "path": info.exe,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    return (
        f"Title: {info.title}\n"
        f"Process: {exe_name}\n"
        f"PID: {info.pid}\n"
        f"HWND: {hwnd_hex}\n"
        f"Class: {info.cls}\n"
        f"Size: {info.width} × {info.height}\n"
        f"Pos: {info.left}, {info.top}\n"
        f"Path: {exe_path}"
    )

def build_overlay_lines(info: WindowInfo, view: str) -> Tuple[str, list[str]]:
    exe_name = os.path.basename(info.exe) if info.exe else "N/A"
    hwnd_hex = f"0x{info.hwnd:08X}"

    if view == "expanded":
        exe_path = info.exe if info.exe else "N/A"
        return info.title, [
            f"Process: {exe_name}",
            f"PID: {info.pid}",
            f"HWND: {hwnd_hex}",
            f"Class: {info.cls}",
            f"Size: {info.width} × {info.height}",
            f"Pos: {info.left}, {info.top}",
            f"Path: {exe_path}",
        ]

    return info.title, [
        f"{exe_name}  •  PID {info.pid}  •  {hwnd_hex}",
        f"{info.width}×{info.height}   @   {info.left},{info.top}",
    ]

# ----------------------------
# Styling (Dark/Light)
# ----------------------------
def apply_app_style(app: QApplication, theme: str):
    theme = "light" if theme == "light" else "dark"
    if theme == "dark":
        app.setStyleSheet("""
            QDialog { background-color: #0f1115; color: #ffffff; }
            QLabel { color: #ffffff; }
            QCheckBox { spacing: 8px; color: #ffffff; }
            QComboBox, QSlider, QPushButton { font-size: 12px; color: #ffffff; }
            QComboBox {
                background-color: #141822;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                padding: 6px 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #141822;
                color: #ffffff;
                border: 1px solid rgba(255,255,255,0.10);
                selection-background-color: rgba(120, 140, 255, 0.25);
                padding: 6px;
            }
            QPushButton {
                background-color: #1a2030;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                padding: 8px 14px;
                color: #ffffff;
            }
            QPushButton:hover { background-color: #222a40; }
            QPushButton:pressed { background-color: #121726; }
            QFrame[card="true"] {
                background-color: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
            }
            QMenu {
                background-color: #141822;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                padding: 8px;
                color: #ffffff;
            }
            QMenu::item { padding: 6px 10px; border-radius: 8px; }
            QMenu::item:selected { background-color: rgba(120, 140, 255, 0.25); }
        """)
    else:
        app.setStyleSheet("""
            QDialog { background-color: #f5f6fa; color: #0b0e14; }
            QLabel { color: #0b0e14; }
            QCheckBox { spacing: 8px; color: #0b0e14; }
            QComboBox, QSlider, QPushButton { font-size: 12px; color: #0b0e14; }
            QComboBox {
                background-color: #ffffff;
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 10px;
                padding: 6px 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #0b0e14;
                border: 1px solid rgba(0,0,0,0.12);
                selection-background-color: rgba(90, 120, 255, 0.20);
                padding: 6px;
            }
            QPushButton {
                background-color: #ffffff;
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 12px;
                padding: 8px 14px;
                color: #0b0e14;
            }
            QPushButton:hover { background-color: #eef1f8; }
            QPushButton:pressed { background-color: #e5e8f2; }
            QFrame[card="true"] {
                background-color: rgba(255,255,255,0.92);
                border: 1px solid rgba(0,0,0,0.10);
                border-radius: 16px;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 12px;
                padding: 8px;
                color: #0b0e14;
            }
            QMenu::item { padding: 6px 10px; border-radius: 8px; }
            QMenu::item:selected { background-color: rgba(90, 120, 255, 0.20); }
        """)

def make_card() -> QFrame:
    fr = QFrame()
    fr.setProperty("card", True)
    fr.setFrameShape(QFrame.NoFrame)
    return fr

# ----------------------------
# UI: Overlays + Blocker + Settings
# ----------------------------
class InfoOverlay(QWidget):
    def __init__(self, cfg: SniperConfig, lang: str):
        super().__init__()
        self.cfg = cfg
        self.lang = lang
        self.theme = cfg.theme

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._title = ""
        self._lines: list[str] = []
        self._copied_until = 0.0
        self._status_line = ""
        self._status_until = 0.0

        self._font_title_base = QFont("Segoe UI", 10)
        self._font_body_base = QFont("Cascadia Mono", 9)
        if not QFontMetrics(self._font_body_base).horizontalAdvance("A"):
            self._font_body_base = QFont("Consolas", 9)

        self._font_ui = QFont("Segoe UI", 9)
        self._font_title = QFont(self._font_title_base)
        self._font_body = QFont(self._font_body_base)

        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(140)
        self._fade.finished.connect(self._on_fade_finished)

        self._pending_hide = False
        self._on_hide_cb = None

        self.setWindowOpacity(0.0)
        self.resize(420, 210)
        self.set_scale(self.cfg.overlay_scale_percent)

    def set_language(self, lang: str):
        self.lang = lang
        self.update()

    def set_theme(self, theme: str):
        self.theme = "light" if theme == "light" else "dark"
        self.update()

    def set_scale(self, percent: int):
        scale = max(80, min(160, int(percent))) / 100.0
        self._font_ui = QFont("Segoe UI", max(8, int(9 * scale)))

        self._font_title = QFont(self._font_title_base)
        self._font_title.setPointSizeF(max(9.5, self._font_title_base.pointSizeF() * scale))
        self._font_title.setBold(True)

        self._font_body = QFont(self._font_body_base)
        self._font_body.setPointSizeF(max(8.5, self._font_body_base.pointSizeF() * scale))

        self._recalc_size()

    def _on_fade_finished(self):
        if self._pending_hide and self.windowOpacity() <= 0.01:
            self._pending_hide = False
            self.hide()
            cb = self._on_hide_cb
            self._on_hide_cb = None
            if cb:
                cb()

    def show_fade_in(self):
        self._fade.stop()
        self._pending_hide = False
        self._on_hide_cb = None
        self.setWindowOpacity(0.0)
        self.show()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def show_fade_out(self, on_done=None):
        self._fade.stop()
        self._pending_hide = True
        self._on_hide_cb = on_done
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    @staticmethod
    def _wrap_friendly(s: str) -> str:
        return s.replace("\\", "\\\u200b").replace("/", "/\u200b")

    def set_content(self, title: str, lines: list[str]):
        self._title = title
        self._lines = lines
        self._recalc_size()
        self.update()

    def flash_copied(self, ms: int = 900):
        self._copied_until = time.time() + (ms / 1000.0)
        self.update()

    def flash_status(self, text: str, ms: int = 1200):
        self._status_line = text
        self._status_until = time.time() + (ms / 1000.0)
        self.update()

    def _recalc_size(self):
        pad = 14
        max_w = 880
        min_w = 360
        max_h = 460

        title = self._wrap_friendly(self._title)
        lines = [self._wrap_friendly(x) for x in self._lines]
        content_w = 760

        fm_t = QFontMetrics(self._font_title)
        fm_b = QFontMetrics(self._font_body)

        br_t = fm_t.boundingRect(QRect(0, 0, content_w, 10_000), Qt.TextWordWrap, title) if title else QRect(0, 0, 0, 0)

        br_lines_h = 0
        br_lines_w = 0
        for ln in lines:
            br = fm_b.boundingRect(QRect(0, 0, content_w, 10_000), Qt.TextWordWrap, ln)
            br_lines_h += br.height()
            br_lines_w = max(br_lines_w, br.width())

        status_h = QFontMetrics(self._font_ui).height() + 12
        w = max(min_w, min(max_w, max(br_t.width(), br_lines_w) + pad * 2 + 10))
        h = min(max_h, br_t.height() + br_lines_h + pad * 2 + status_h + 14)

        if w != self.width() or h != self.height():
            self.resize(w, h)

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        dark = (self.theme != "light")
        if dark:
            shadow_base = 58
            bg_top = QColor(18, 20, 26, 235)
            bg_bottom = QColor(10, 12, 16, 220)
            border = QColor(255, 255, 255, 30)
            title_col = QColor(255, 255, 255, 245)  # white on dark
            body_col = QColor(255, 255, 255, 235)
            status_col = QColor(255, 255, 255, 210)
        else:
            shadow_base = 38
            bg_top = QColor(255, 255, 255, 250)
            bg_bottom = QColor(240, 242, 247, 250)
            border = QColor(0, 0, 0, 24)
            title_col = QColor(10, 12, 16, 245)
            body_col = QColor(20, 24, 33, 235)
            status_col = QColor(25, 30, 40, 210)

        for i in range(1, 7):
            alpha = max(0, shadow_base - i * 9)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(2 + i, 4 + i, w - (4 + i * 2), h - (6 + i * 2), 16, 16)

        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, bg_top)
        bg.setColorAt(1.0, bg_bottom)
        p.setBrush(bg)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(2, 2, w - 4, h - 4, 16, 16)

        pad = 14
        x = pad
        y = pad

        p.setPen(title_col)
        p.setFont(self._font_title)
        title = self._wrap_friendly(self._title)
        title_rect = QRect(x, y, w - pad * 2, h)
        br_t = QFontMetrics(self._font_title).boundingRect(title_rect, Qt.TextWordWrap, title) if title else QRect(0, 0, 0, 0)
        p.drawText(title_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, title)
        y += br_t.height() + 8

        p.setFont(self._font_body)
        p.setPen(body_col)
        for ln in self._lines:
            ln = self._wrap_friendly(ln)
            r = QRect(x, y, w - pad * 2, h)
            br = QFontMetrics(self._font_body).boundingRect(r, Qt.TextWordWrap, ln)
            p.drawText(r, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, ln)
            y += br.height()

        parts = []
        if time.time() < self._copied_until:
            parts.append(tr(self.lang, "status_copied"))
        if time.time() < self._status_until and self._status_line:
            parts.append(self._status_line)

        if parts:
            p.setFont(self._font_ui)
            p.setPen(status_col)
            p.drawText(pad, h - 12, "   ".join(parts))

class OutlineOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.theme = "dark"
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowTransparentForInput, True)
        self._thickness = 2
        self._margin = 2
        self.hide()

    def set_theme(self, theme: str):
        self.theme = "light" if theme == "light" else "dark"
        self.update()

    def set_rect(self, left, top, width, height):
        m = self._margin
        self.setGeometry(left - m, top - m, width + 2 * m, height + 2 * m)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(120, 140, 255, 220) if self.theme != "light" else QColor(60, 90, 255, 200)
        pen = QPen(col, self._thickness)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.transparent)
        p.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 10, 10)

class InputBlocker(QWidget):
    """
    Fullscreen transparent window capturing input -> prevents clicks reaching other apps.
    IMPORTANT: must NOT be fully transparent (alpha 0), otherwise Windows may pass clicks through.
    """
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(QCursor(Qt.CrossCursor))
        self.setMouseTracking(True)

    def show_with_geometry(self):
        vx, vy, vw, vh = get_virtual_screen_rect()
        self.setGeometry(vx, vy, vw, vh)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)

        hwnd = int(self.winId())
        clear_ws_ex_transparent(hwnd)
        enforce_topmost(hwnd)

        # Hard capture inside Qt (helps when focus is weird)
        try:
            self.grabMouse()
        except Exception:
            pass
        try:
            self.grabKeyboard()
        except Exception:
            pass

    def release_capture(self):
        try:
            self.releaseMouse()
        except Exception:
            pass
        try:
            self.releaseKeyboard()
        except Exception:
            pass

    def paintEvent(self, event):
        # Key fix: draw alpha=1 across entire window so it is hit-testable but visually invisible.
        p = QPainter(self)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 1))  # almost invisible, but blocks clicks
        p.drawRect(self.rect())

    def mousePressEvent(self, event):
        if not self.controller.enabled:
            event.accept()
            return
        if time.time() < self.controller.ignore_mouse_until:
            event.accept()
            return
        if time.time() < self.controller.action_cooldown_until:
            event.accept()
            return

        if event.button() == Qt.RightButton:
            self.controller.disable()
        elif event.button() == Qt.LeftButton:
            self.controller.copy_current()

        event.accept()

    def keyPressEvent(self, event):
        if not self.controller.enabled:
            event.accept()
            return
        if time.time() < self.controller.action_cooldown_until:
            event.accept()
            return

        k = event.key()
        if k == Qt.Key_Escape:
            self.controller.disable()
        elif k == Qt.Key_Space:
            self.controller.toggle_pin()
        elif k == Qt.Key_M:
            self.controller.cycle_copy_format()
        elif k == Qt.Key_Tab:
            self.controller.toggle_view()
        event.accept()

class SettingsDialog(QDialog):
    def __init__(self, cfg: SniperConfig, lang: str, on_apply: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.lang = lang
        self.on_apply = on_apply

        self.setWindowTitle(tr(lang, "settings_title"))
        self.setMinimumWidth(590)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # Behavior
        card1 = make_card()
        c1 = QVBoxLayout(card1)
        c1.setContentsMargins(14, 14, 14, 14)
        c1.setSpacing(10)
        title1 = QLabel(tr(lang, "sec_behavior"))
        title1.setStyleSheet("font-weight: 700; font-size: 14px;")
        c1.addWidget(title1)
        self.lbl_sec_behavior = title1
        self.lbl_sec_visual = title1
        self.lbl_sec_language = title1

        self.cb_block = QCheckBox(tr(lang, "opt_block_clicks"))
        self.cb_block.setChecked(cfg.block_clicks)
        c1.addWidget(self.cb_block)

        self.cb_autoexit = QCheckBox(tr(lang, "opt_auto_exit"))
        self.cb_autoexit.setChecked(cfg.auto_exit_after_copy)
        c1.addWidget(self.cb_autoexit)

        self.cb_outline = QCheckBox(tr(lang, "opt_show_outline"))
        self.cb_outline.setChecked(cfg.show_outline)
        c1.addWidget(self.cb_outline)

        root.addWidget(card1)

        # Visual
        card2 = make_card()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(14, 14, 14, 14)
        c2.setSpacing(12)
        title2 = QLabel(tr(lang, "sec_visual"))
        title2.setStyleSheet("font-weight: 700; font-size: 14px;")
        c2.addWidget(title2)
        self.lbl_sec_behavior = title2
        self.lbl_sec_visual = title2
        self.lbl_sec_language = title2

        def row(label: str, w: QWidget) -> QLabel:
            lay = QHBoxLayout()
            lay.setSpacing(12)
            lbl = QLabel(label)
            lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            lay.addWidget(lbl)
            lay.addWidget(w, 1)
            c2.addLayout(lay)
            return lbl

        self.combo_theme = QComboBox()
        self.combo_theme.addItem(tr(lang, "theme_dark"), "dark")
        self.combo_theme.addItem(tr(lang, "theme_light"), "light")
        self._set_combo_by_data(self.combo_theme, cfg.theme)
        self.lbl_theme = row(tr(lang, "opt_theme") + ":", self.combo_theme)

        self.combo_blur = QComboBox()
        self.combo_blur.addItem(tr(lang, "blur_auto"), "auto")
        self.combo_blur.addItem(tr(lang, "blur_on"), "on")
        self.combo_blur.addItem(tr(lang, "blur_off"), "off")
        self._set_combo_by_data(self.combo_blur, cfg.blur_mode)
        self.lbl_blur = row(tr(lang, "opt_blur") + ":", self.combo_blur)

        self.combo_view = QComboBox()
        self.combo_view.addItem(tr(lang, "view_compact"), "compact")
        self.combo_view.addItem(tr(lang, "view_expanded"), "expanded")
        self._set_combo_by_data(self.combo_view, cfg.default_view)
        self.lbl_default_view = row(tr(lang, "opt_default_view") + ":", self.combo_view)

        self.combo_fmt = QComboBox()
        self.combo_fmt.addItem(tr(lang, "fmt_text"), 0)
        self.combo_fmt.addItem(tr(lang, "fmt_markdown"), 1)
        self.combo_fmt.addItem(tr(lang, "fmt_json"), 2)
        self._set_combo_by_data(self.combo_fmt, cfg.copy_format_idx)
        self.lbl_copy_format = row(tr(lang, "opt_copy_format") + ":", self.combo_fmt)

        scale_row = QHBoxLayout()
        self.scale_label = QLabel(f"{cfg.overlay_scale_percent}%")
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setMinimum(80)
        self.scale_slider.setMaximum(160)
        self.scale_slider.setValue(cfg.overlay_scale_percent)
        self.scale_slider.valueChanged.connect(lambda v: self.scale_label.setText(f"{int(v)}%"))
        scale_row.addWidget(self.scale_slider, 1)
        scale_row.addWidget(self.scale_label)
        wrap = QWidget()
        wrap.setLayout(scale_row)
        self.lbl_scale = row(tr(lang, "opt_scale") + ":", wrap)

        root.addWidget(card2)

        # Language
        card3 = make_card()
        c3 = QVBoxLayout(card3)
        c3.setContentsMargins(14, 14, 14, 14)
        c3.setSpacing(12)
        title3 = QLabel(tr(lang, "sec_language"))
        title3.setStyleSheet("font-weight: 700; font-size: 14px;")
        c3.addWidget(title3)
        self.lbl_sec_behavior = title3
        self.lbl_sec_language = title3
        self.lbl_sec_visual = title3

        self.combo_lang = QComboBox()
        self.combo_lang.addItem(tr(lang, "lang_auto"), "auto")
        self.combo_lang.addItem(tr(lang, "lang_en"), "en")
        self.combo_lang.addItem(tr(lang, "lang_ru"), "ru")
        self._set_combo_by_data(self.combo_lang, cfg.language)

        lay_lang = QHBoxLayout()
        lay_lang.setSpacing(12)
        lbl_lang = QLabel(tr(lang, "opt_language") + ":")
        self.lbl_language = lbl_lang
        lbl_lang.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        lay_lang.addWidget(lbl_lang)
        lay_lang.addWidget(self.combo_lang, 1)
        c3.addLayout(lay_lang)

        root.addWidget(card3)

        # Buttons: Cancel / Apply / Save
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.btn_cancel = QPushButton(tr(lang, "btn_cancel"))
        self.btn_apply = QPushButton(tr(lang, "btn_apply"))
        self.btn_save = QPushButton(tr(lang, "btn_save"))

        self.btn_save.setStyleSheet("background-color: rgba(120, 140, 255, 0.20); border: 1px solid rgba(120, 140, 255, 0.35);")
        self.btn_apply.setStyleSheet("background-color: rgba(120, 140, 255, 0.10); border: 1px solid rgba(120, 140, 255, 0.22);")

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self.accept)
        self.btn_apply.clicked.connect(self._apply_no_close)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, data):
        for i in range(combo.count()):
            if combo.itemData(i) == data:
                combo.setCurrentIndex(i)
                return

    def _rebuild_combo(self, combo: QComboBox, items: list[tuple[str, object]]):
        cur = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for text, data in items:
            combo.addItem(text, data)
        # restore selection
        for i in range(combo.count()):
            if combo.itemData(i) == cur:
                combo.setCurrentIndex(i)
                break
        combo.blockSignals(False)

    def retranslate(self, lang: str):
        self.lang = lang
        self.setWindowTitle(tr(lang, "settings_title"))

        # section titles
        self.lbl_sec_behavior.setText(tr(lang, "sec_behavior"))
        self.lbl_sec_visual.setText(tr(lang, "sec_visual"))
        self.lbl_sec_language.setText(tr(lang, "sec_language"))

        # checkboxes
        self.cb_block.setText(tr(lang, "opt_block_clicks"))
        self.cb_autoexit.setText(tr(lang, "opt_auto_exit"))
        self.cb_outline.setText(tr(lang, "opt_show_outline"))

        # row labels
        self.lbl_theme.setText(tr(lang, "opt_theme") + ":")
        self.lbl_blur.setText(tr(lang, "opt_blur") + ":")
        self.lbl_default_view.setText(tr(lang, "opt_default_view") + ":")
        self.lbl_copy_format.setText(tr(lang, "opt_copy_format") + ":")
        self.lbl_scale.setText(tr(lang, "opt_scale") + ":")
        self.lbl_language.setText(tr(lang, "opt_language") + ":")

        # combos (keep selection)
        self._rebuild_combo(self.combo_theme, [
            (tr(lang, "theme_dark"), "dark"),
            (tr(lang, "theme_light"), "light"),
        ])
        self._rebuild_combo(self.combo_blur, [
            (tr(lang, "blur_auto"), "auto"),
            (tr(lang, "blur_on"), "on"),
            (tr(lang, "blur_off"), "off"),
        ])
        self._rebuild_combo(self.combo_view, [
            (tr(lang, "view_compact"), "compact"),
            (tr(lang, "view_expanded"), "expanded"),
        ])
        self._rebuild_combo(self.combo_fmt, [
            (tr(lang, "fmt_text"), 0),
            (tr(lang, "fmt_markdown"), 1),
            (tr(lang, "fmt_json"), 2),
        ])
        self._rebuild_combo(self.combo_lang, [
            (tr(lang, "lang_auto"), "auto"),
            (tr(lang, "lang_en"), "en"),
            (tr(lang, "lang_ru"), "ru"),
        ])

        # buttons
        self.btn_cancel.setText(tr(lang, "btn_cancel"))
        self.btn_apply.setText(tr(lang, "btn_apply"))
        self.btn_save.setText(tr(lang, "btn_save"))

    def apply_to_cfg(self):
        self.cfg.block_clicks = bool(self.cb_block.isChecked())
        self.cfg.auto_exit_after_copy = bool(self.cb_autoexit.isChecked())
        self.cfg.show_outline = bool(self.cb_outline.isChecked())
        self.cfg.theme = self.combo_theme.currentData()
        self.cfg.blur_mode = self.combo_blur.currentData()
        self.cfg.default_view = self.combo_view.currentData()
        self.cfg.copy_format_idx = int(self.combo_fmt.currentData())
        self.cfg.overlay_scale_percent = int(self.scale_slider.value())
        self.cfg.language = self.combo_lang.currentData()

    def _apply_no_close(self):
        self.apply_to_cfg()
        if self.on_apply:
            new_lang = self.on_apply()  # ожидаем "ru"/"en"
            if new_lang:
                self.retranslate(new_lang)


# ----------------------------
# Main app
# ----------------------------
class WindowSniperApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.cfg = load_config()
        self.lang = resolve_lang(self.cfg.language)
        apply_app_style(self.app, self.cfg.theme)

        self.enabled = False
        self.pinned = False
        self.view = self.cfg.default_view
        self._last_info: Optional[WindowInfo] = None

        self.ignore_mouse_until = 0.0
        self.action_cooldown_until = 0.0
        self._switch_view_until = 0.0
        self._switch_fmt_until = 0.0
        self._toggle_until = 0.0

        self.overlay = InfoOverlay(self.cfg, self.lang)
        self.outline = OutlineOverlay()
        self.blocker = InputBlocker(self)

        self.overlay.set_theme(self.cfg.theme)
        self.outline.set_theme(self.cfg.theme)

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)

        self._keypoll = QTimer()
        self._keypoll.timeout.connect(self._poll_keyboard_edges)

        self._prev = {"esc": False, "space": False, "m": False, "tab": False, "rmb": False}

        self._tray = self._create_tray()
        self._register_hotkey()

        logger.info("Started. cfg=%s", asdict(self.cfg))

    # ---- Tray
    def _make_crosshair_icon(self, active: bool = False) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(120, 140, 255, 240) if active else QColor(255, 255, 255, 240)
        pen = QPen(col, 4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(32, 8, 32, 24)
        p.drawLine(32, 40, 32, 56)
        p.drawLine(8, 32, 24, 32)
        p.drawLine(40, 32, 56, 32)
        p.drawEllipse(18, 18, 28, 28)
        p.end()
        return QIcon(pix)

    def _create_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self._make_crosshair_icon(active=False))
        self._tray = tray  # important

        self._tray_menu = QMenu()

        self._act_toggle = QAction("")
        self._act_toggle.triggered.connect(self.toggle)

        self._act_copy = QAction("")
        self._act_copy.triggered.connect(self.copy_current)

        self._act_pin = QAction("")
        self._act_pin.triggered.connect(self.toggle_pin)

        self._act_view = QAction("")
        self._act_view.triggered.connect(self.toggle_view)

        self._fmt_menu = QMenu("")
        self._fmt_actions = []
        for idx, key in enumerate(COPY_FORMAT_KEYS):
            a = QAction("")
            a.setCheckable(True)
            a.triggered.connect(lambda checked, i=idx: self.set_copy_format(i))
            self._fmt_actions.append(a)
            self._fmt_menu.addAction(a)

        self._act_settings = QAction("")
        self._act_settings.triggered.connect(self.open_settings)

        self._act_about = QAction("")
        self._act_about.triggered.connect(self.open_about)

        self._act_exit = QAction("")
        self._act_exit.triggered.connect(self.quit)

        self._tray_menu.addAction(self._act_toggle)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction(self._act_copy)
        self._tray_menu.addAction(self._act_pin)
        self._tray_menu.addAction(self._act_view)
        self._tray_menu.addMenu(self._fmt_menu)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction(self._act_settings)
        self._tray_menu.addAction(self._act_about)
        self._tray_menu.addAction(self._act_exit)

        tray.setContextMenu(self._tray_menu)
        tray.activated.connect(self._on_tray_activated)

        self._apply_language_to_ui()
        self._sync_tray_checks()

        tray.show()
        return tray

    def _apply_language_to_ui(self):
        self._act_toggle.setText(tr(self.lang, "tray_toggle"))
        self._act_copy.setText(tr(self.lang, "tray_copy"))
        self._act_pin.setText(tr(self.lang, "tray_pin"))
        self._act_view.setText(tr(self.lang, "tray_view"))
        self._act_settings.setText(tr(self.lang, "tray_settings"))
        self._act_about.setText(tr(self.lang, "tray_about"))
        self._act_exit.setText(tr(self.lang, "tray_exit"))

        self._fmt_menu.setTitle(tr(self.lang, "tray_copy_format"))
        for idx, key in enumerate(COPY_FORMAT_KEYS):
            self._fmt_actions[idx].setText(tr(self.lang, key))

        self._tray.setToolTip(tr(self.lang, "app_name"))
        self.overlay.set_language(self.lang)

    def _sync_tray_checks(self):
        for i, a in enumerate(self._fmt_actions):
            a.setChecked(i == self.cfg.copy_format_idx)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle()
        elif reason == QSystemTrayIcon.Context:
            self._tray_menu.popup(QCursor.pos())

    # ---- Hotkey
    def _register_hotkey(self):
        if not user32.RegisterHotKey(None, HOTKEY_ID, HOTKEY_MODS, HOTKEY_VK):
            self._tray.showMessage(tr(self.lang, "mode_title"), tr(self.lang, "hotkey_fail"), QSystemTrayIcon.Warning)
        self._hotkey_filter = WinHotkeyFilter(HOTKEY_ID, self.toggle)
        self.app.installNativeEventFilter(self._hotkey_filter)

    def _unregister_hotkey(self):
        try:
            user32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception:
            pass

    # ---- Cooldowns
    def _cooldown(self, ms: int) -> float:
        return time.time() + (ms / 1000.0)

    def _switch_cd(self) -> int:
        return int(self.cfg.switch_cooldown_ms)

    # ---- Actions
    def set_copy_format(self, idx: int):
        if time.time() < self._switch_fmt_until:
            return
        self._switch_fmt_until = self._cooldown(self._switch_cd())

        idx = int(max(0, min(2, idx)))
        self.cfg.copy_format_idx = idx
        save_config(self.cfg)
        self._sync_tray_checks()
        self.overlay.flash_status(tr(self.lang, "status_format", f=tr(self.lang, COPY_FORMAT_KEYS[idx])), 1100)

    def cycle_copy_format(self):
        self.set_copy_format((self.cfg.copy_format_idx + 1) % 3)

    def toggle_view(self):
        if time.time() < self._switch_view_until:
            return
        self._switch_view_until = self._cooldown(self._switch_cd())

        self.view = "expanded" if self.view == "compact" else "compact"
        v_txt = tr(self.lang, "view_expanded") if self.view == "expanded" else tr(self.lang, "view_compact")
        self.overlay.flash_status(tr(self.lang, "status_view", v=v_txt), 1100)

    def toggle_pin(self):
        if not self.enabled:
            return
        self.pinned = not self.pinned
        self.overlay.flash_status(tr(self.lang, "status_pinned") if self.pinned else tr(self.lang, "status_unpinned"), 900)

    def copy_current(self):
        if not self._last_info:
            return
        text = format_info_for_clipboard(self._last_info, self.cfg.copy_format_idx)
        QGuiApplication.clipboard().setText(text)
        self.overlay.flash_copied(900)

        # tiny cooldown after copy, so no accidental tab/m spam right away
        self.action_cooldown_until = self._cooldown(160)

        if self.cfg.auto_exit_after_copy and self.enabled:
            QTimer.singleShot(450, self.disable)

    # ---- Mode lifecycle
    def toggle(self):
        # small toggle delay to avoid double-trigger on hotkey repeats
        if time.time() < self._toggle_until:
            return
        self._toggle_until = self._cooldown(250)

        if self.enabled:
            self.disable()
        else:
            self.enable()

    def _prime_keyboard_prev(self):
        self._prev["esc"] = is_key_down(VK_ESCAPE)
        self._prev["space"] = is_key_down(VK_SPACE)
        self._prev["m"] = is_key_down(VK_M)
        self._prev["tab"] = is_key_down(VK_TAB)
        self._prev["rmb"] = is_key_down(VK_RBUTTON)

    def enable(self):
        if self.enabled:
            return

        self.enabled = True
        self.pinned = False
        self._last_info = None
        self.view = self.cfg.default_view

        self.ignore_mouse_until = time.time() + 0.30
        self.action_cooldown_until = time.time() + 0.22
        self._switch_view_until = 0.0
        self._switch_fmt_until = 0.0

        self._tray.setIcon(self._make_crosshair_icon(active=True))
        QApplication.setOverrideCursor(QCursor(Qt.CrossCursor))

        # Apply theme to overlays
        self.overlay.set_theme(self.cfg.theme)
        self.outline.set_theme(self.cfg.theme)

        # Show blocker to prevent clicks reaching apps
        self.blocker.show_with_geometry()

        # Overlay + outline
        self.overlay.show_fade_in()
        if self.cfg.show_outline:
            self.outline.show()
        else:
            self.outline.hide()

        # Make overlay/outline click-through (blocker must receive input)
        set_click_through(int(self.overlay.winId()), True)
        set_click_through(int(self.outline.winId()), True)

        # Blur (theme-aware)
        apply_blur_mode(int(self.overlay.winId()), self.cfg.blur_mode, self.cfg.theme)

        self._timer.start(int(self.cfg.update_ms))
        self._prime_keyboard_prev()
        self._keypoll.start(int(self.cfg.keyboard_poll_ms))

        QTimer.singleShot(0, self._tick)

        self.overlay.flash_status(tr(self.lang, "status_hint_blocked"), 1800)
        self._tray.showMessage(tr(self.lang, "mode_title"), tr(self.lang, "mode_on"), QSystemTrayIcon.Information)

    def disable(self):
        if not self.enabled:
            return

        self.enabled = False
        self.pinned = False

        self._timer.stop()
        self._keypoll.stop()

        self.outline.hide()
        self.overlay.show_fade_out()

        self.blocker.release_capture()
        self.blocker.hide()

        self._tray.setIcon(self._make_crosshair_icon(active=False))
        try:
            QApplication.restoreOverrideCursor()
        except Exception:
            pass

        self._tray.showMessage(tr(self.lang, "mode_title"), tr(self.lang, "mode_off"), QSystemTrayIcon.Information)

    # ---- Keyboard polling fallback
    def _poll_keyboard_edges(self):
        if not self.enabled:
            return

        now_esc = is_key_down(VK_ESCAPE)
        now_space = is_key_down(VK_SPACE)
        now_m = is_key_down(VK_M)
        now_tab = is_key_down(VK_TAB)
        now_rmb = is_key_down(VK_RBUTTON)

        def rising(now: bool, prev: bool) -> bool:
            return now and not prev

        # RMB exit fallback (blocker should handle RMB, but this helps if capture breaks)
        if rising(now_rmb, self._prev["rmb"]) and time.time() >= self.ignore_mouse_until:
            self.disable()
            self._prev["rmb"] = now_rmb
            return

        if rising(now_esc, self._prev["esc"]):
            self.disable()
            self._prev["esc"] = now_esc
            return

        if rising(now_space, self._prev["space"]):
            if time.time() >= self.action_cooldown_until:
                self.toggle_pin()

        if rising(now_m, self._prev["m"]):
            if time.time() >= self.action_cooldown_until:
                self.cycle_copy_format()

        if rising(now_tab, self._prev["tab"]):
            if time.time() >= self.action_cooldown_until:
                self.toggle_view()

        self._prev["esc"] = now_esc
        self._prev["space"] = now_space
        self._prev["m"] = now_m
        self._prev["tab"] = now_tab
        self._prev["rmb"] = now_rmb

    # ---- Update loop (window under cursor)
    def _tick(self):
        if not self.enabled:
            return
        if self.pinned and self._last_info:
            self.blocker.raise_()
            self.overlay.raise_()
            if self.cfg.show_outline:
                self.outline.raise_()
            return

        cx, cy = get_cursor_pos()
        hwnd = get_hwnd_under_cursor_scan_zorder(cx, cy, ignore_pid=os.getpid())
        info = collect_window_info(hwnd) if hwnd else None
        if not info:
            return

        self._last_info = info

        title, lines = build_overlay_lines(info, self.view)
        self.overlay.set_content(title, lines)

        w, h = self.overlay.width(), self.overlay.height()
        nx, ny = clamp_overlay_pos(cx + int(self.cfg.overlay_offset_x), cy + int(self.cfg.overlay_offset_y), w, h)
        self.overlay.move(nx, ny)

        if self.cfg.show_outline:
            self.outline.set_rect(info.left, info.top, info.width, info.height)
            self.outline.show()
        else:
            self.outline.hide()

        # keep ordering stable
        self.blocker.raise_()
        self.overlay.raise_()
        if self.cfg.show_outline:
            self.outline.raise_()

    # ---- Settings applying (Save vs Apply)
    def _apply_settings_live(self) -> str:
        save_config(self.cfg)

        apply_app_style(self.app, self.cfg.theme)
        self.lang = resolve_lang(self.cfg.language)
        self._apply_language_to_ui()
        self._sync_tray_checks()

        self.overlay.set_scale(self.cfg.overlay_scale_percent)
        self.overlay.set_theme(self.cfg.theme)
        self.outline.set_theme(self.cfg.theme)

        if self.enabled:
            apply_blur_mode(int(self.overlay.winId()), self.cfg.blur_mode, self.cfg.theme)
            if not self.cfg.show_outline:
                self.outline.hide()
            self.blocker.show_with_geometry()
            self.blocker.raise_()
            self.overlay.flash_status(tr(self.lang, "status_settings_applied"), 1100)

        logger.info("Settings applied. cfg=%s", asdict(self.cfg))
        return self.lang

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self.lang, on_apply=self._apply_settings_live, parent=None)
        if dlg.exec() == QDialog.Accepted:
            dlg.apply_to_cfg()
            self._apply_settings_live()

    def open_about(self):
        title = tr(self.lang, "about_title")

        tag = AUTHOR_TAG.strip()
        if tag and not tag.startswith("@"):
            tag = "@" + tag
        tag = f"({tag})" if tag else ""

        body = tr(
            self.lang,
            "about_body",
            ver=APP_VERSION,
            author=AUTHOR_NAME,
            tag=tag,
            build=BUILD_DATE,
            copyright=COPYRIGHT,
            license=LICENSE_NAME,
            cfg=CFG_PATH,
            log=LOG_PATH,
        )

        QMessageBox.information(None, title, body)


    # ---- Exit
    def quit(self):
        self.disable()
        self._unregister_hotkey()
        self._tray.hide()
        save_config(self.cfg)
        self.app.quit()

    def run(self):
        self.app.exec()

# ----------------------------
# Entry
# ----------------------------
if __name__ == "__main__":
    WindowSniperApp().run()
