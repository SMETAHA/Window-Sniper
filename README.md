# Window Sniper

Lightweight tool for inspecting windows under the cursor in Windows OS.

---

## 🌐 Language

<details open>
<summary><b>🇺🇸 English</b></summary>

---

### 📌 Description
Window Sniper is a desktop tool that allows you to inspect and retrieve information about windows under the cursor in real time.

The project demonstrates working with Windows API, system-level data, and custom UI overlays.

---

### ⚙️ Features
- real-time window detection under cursor  
- extraction of window properties (title, class, PID, size, position)  
- overlay interface with dynamic updates  
- input blocking mode (sniper mode)  
- global hotkeys support  
- multiple output formats (Text / Markdown / JSON)  
- configurable UI (theme, scaling, blur, language)  

---

### 🛠 Tech Stack
- Python  
- PySide6 (Qt)  
- Windows API (ctypes)  

---

### 💡 Implementation Highlights
- direct interaction with WinAPI using ctypes  
- custom overlay rendering with Qt  
- global hotkey handling via native events  
- input interception using fullscreen blocker  
- configuration system with persistent storage  
- multi-language support (RU / EN)  

---

### 🚀 Usage
Run the script on Windows:

```bash
python window_sniper.py
