# Window Sniper

Lightweight Windows utility for inspecting the window under the cursor in real time.

---

## 🌐 Language

<details open>
<summary><b>🇺🇸 English</b></summary>

---

### 📌 Description
Window Sniper is a desktop utility for inspecting and collecting information about windows under the cursor in real time.

The project demonstrates working with Windows API, native hotkeys, custom overlay rendering, input blocking, persistent configuration, and multilingual UI.

---

### ⚙️ Features
- real-time window detection under cursor
- extraction of window properties:
  - title
  - class name
  - PID
  - executable path
  - size and position
- overlay UI with compact and expanded views
- Sniper Mode with click blocking
- global hotkey support
- pin/unpin target window
- multiple copy formats:
  - Text
  - Markdown
  - JSON
- configurable theme, blur, scaling, language, and behavior
- tray integration

---

### 🛠 Tech Stack
- Python
- PySide6
- Windows API via `ctypes`

---

### 💡 Implementation Highlights
- WinAPI interaction through `ctypes`
- custom topmost overlays and outline rendering
- native hotkey handling
- fullscreen input blocker to prevent click-through
- config storage in AppData
- RU / EN localization
- logging with rotating log files

---

### 🚀 Run
```bash
python window_sniper.py
```

Hotkey:
```text
Ctrl + Alt + S
```

---

### ⚠️ Notes
- Windows only
- Requires `PySide6`

</details>

---

<details>
<summary><b>🇷🇺 Русский</b></summary>

---

### 📌 Описание
Window Sniper — десктопный инструмент для получения информации об окнах под курсором в реальном времени.

Проект демонстрирует работу с Windows API, глобальными хоткеями, кастомным overlay-интерфейсом, блокировкой ввода, конфигами и многоязычным UI.

---

### ⚙️ Возможности
- определение окна под курсором в реальном времени
- получение свойств окна:
  - заголовок
  - класс окна
  - PID
  - путь к исполняемому файлу
  - размер и позиция
- overlay-интерфейс с компактным и расширенным видом
- режим Sniper Mode с блокировкой кликов
- поддержка глобальной горячей клавиши
- закрепление / открепление текущего окна
- несколько форматов копирования:
  - Text
  - Markdown
  - JSON
- настройка темы, размытия, масштаба, языка и поведения
- интеграция с системным треем

---

### 🛠 Стек
- Python
- PySide6
- Windows API через `ctypes`

---

### 💡 Особенности реализации
- работа с WinAPI через `ctypes`
- собственные topmost-overlay окна и подсветка рамкой
- обработка нативного хоткея
- fullscreen-блокировщик ввода без low-level hooks
- хранение конфигурации в AppData
- локализация RU / EN
- логирование с ротацией логов

---

### 🚀 Запуск
```bash
python window_sniper.py
```

Горячая клавиша:
```text
Ctrl + Alt + S
```

---

### ⚠️ Важно
- только для Windows
- требуется `PySide6`

</details>
