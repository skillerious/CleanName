# 🚧 WIP — CleanNames (v2.9.2)

> **Alpha / Heavy Development**  
> This project is under **active and heavy development** 🛠️—expect missing features, experimental APIs, and frequent breaking changes.

---

## 📋 About

**CleanNames** is an open‑source, dark‑themed batch file/folder renamer built in Python with Qt (PySide6).  
It runs as a standalone `main.py` script, providing a powerful GUI to clean up, standardize, and organize filenames using:

- **Bad‑character stripping/replacement**  
- **Sequential numbering**  
- **Regex‑based find & replace**  
- **Photo EXIF metadata renaming**  

Whether you’re tidying code repos, organizing photo collections, or mass‑renaming logs, CleanNames has you covered!

---

## 🚀 Key Features (In‑Depth)

1. **Remove / Replace Bad Characters**  
   - Define a custom set of “bad” characters (e.g., `"#%*:<>?/|`) to strip or replace with a single placeholder.  
   - Handles Windows reserved names (e.g., `CON`, `PRN`) automatically.

2. **Sequential Renaming**  
   - Apply a user‑defined prefix plus incrementing numbers:  
     ```
     item1.txt, item2.txt, item3.txt, …
     ```  
   - Choose the starting index.

3. **Regex Rename**  
   - Enter any regex and replacement string for advanced batch transformations.  
   - Use capture groups, lookaround, and more for precision renames.

4. **Metadata (Photo Date)**  
   - Automatically extract EXIF “DateTimeOriginal” or file‑modified timestamp.  
   - Rename photos like `2023-05-10_14-22-01.jpg` for chronological sorting.

5. **Live Folder Watch**  
   - Toggle “Watch & Auto‑Rename” mode to reapply last used rules whenever the folder changes.  
   - Great for hot‑folder workflows.

6. **Undo Last Batch**  
   - One‑click revert of the previous rename operations (stored in `last_batch.json`).

7. **Smart Icons**  
   - PNG icons per file extension, category fallbacks, or built‑in Qt icons.  
   - Cached for speed, logged if missing.

8. **Dark Fusion Theme**  
   - Built‑in dark mode with accent color (#2080ff).  
   - Toggleable via Preferences.

---

## 💡 Installation & Setup

1. **Clone the repo**  
   ```bash
   git clone https://github.com/skillerious/CleanNames.git
   cd CleanNames
   ```

2. **Create and activate a virtual environment**  
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**  
   ```bash
   pip install -r requirements.txt
   ```
   - **PySide6** for the GUI  
   - **Pillow** (optional) for EXIF metadata support  

---

## 🏃‍♂️ Running the Application

Launch the GUI with:
```bash
python main.py
```

### Workflow

1. **Select Target Folder**  
2. **Choose Modes & Options**  
3. **Pick Extensions** (check/uncheck file types)  
4. **Preview**: see a list of planned renames  
5. **Rename**: execute the batch  
6. **Undo** if needed

---

## 🌟 Customization & Settings

- **Remember Last Folder**: stores your most recent directory.  
- **Default Recursive**: set whether subfolders are included by default.  
- **Dark Theme Toggle**: switch between light/dark.  
- **Header & Splitter State**: columns and panels remember their sizes/layout.

All preferences are saved in `~/.config/Skillerious/clean_names.ini` (platform paths via QStandardPaths).

---

## 🔮 Roadmap

- ✅ **Photo metadata** (EXIF)  
- 🔄 **Auto‑watch improvements**  
- 🚧 Drag‑and‑drop support  
- ⚡ Speed & threading optimizations  
- 🎨 Additional themes & icon packs  
- 🐧 Packaging for Linux/macOS/AppImage

---

## 🤝 Contributing

Contributions are **welcome**! Steps:

1. Fork the repo  
2. Create a branch:  
   ```bash
   git checkout -b feature/YourFeature
   ```
3. Commit your changes  
4. Push branch & open a PR  

Please follow PEP8 style and include docstrings/tests where possible.

---

## 📜 License

Released under the **MIT License**. See [LICENSE](LICENSE) for details.

---

> Built with ❤️ by Robin Doak  
> https://github.com/skillerious
