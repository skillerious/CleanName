#!/usr/bin/env python3
"""
Clean Names GUI (v 2.9.2 – kitchen-sink)
========================================
 • Robust, cached PNG icons: exact ext → category → fallback → Qt builtin
 • Logs missing icon names in status bar for easy debugging
 • Table iconSize 16px, smooth scrolling
 • Thread‐ and watcher‐lifetime fixed
 • Full regex / sequential / metadata / auto-watch / undo feature set
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

from PySide6.QtCore    import (
    Qt,
    QSize,
    QAbstractTableModel,
    QByteArray,
    QFileSystemWatcher,
    QSettings,
    QSortFilterProxyModel,
    QStandardPaths,
    QThread,
    QTimer,
    QModelIndex,
    Signal,
)
from PySide6.QtGui     import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QStyle,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
)

# ────────── paths / constants ─────────────────────────────────────────
APP_NAME   = "CleanNames"
ORG_NAME   = "Skillerious"
VERSION    = "2.9.2"

ASSETS     = Path(__file__).with_name("assets")
ICONS_DIR  = ASSETS / "icons"   # place your PNGs here

LOGO_PNG   = ASSETS / "logo.png"
OPEN_PNG   = ASSETS / "open_folder.png"
UNDO_PNG   = ASSETS / "undo.png"
SET_PNG    = ASSETS / "settings.png"
HELP_PNG   = ASSETS / "help.png"
INFO_PNG   = ASSETS / "info.png"
CHECK_PNG  = ASSETS / "checkmark.png"
HELP_HTML  = Path(__file__).with_name("help.html")

DEFAULT_BAD_CHARS: Set[str] = set("\"#%*:<>?/|")
DEFAULT_EXTS      = (".txt", ".py", ".md", ".csv", ".json")
PHOTO_EXTS        = {".jpg", ".jpeg", ".tif", ".tiff", ".png"}
WIN_RESERVED      = {
    "con","prn","aux","nul",
    *(f"com{i}" for i in range(1,10)),
    *(f"lpt{i}" for i in range(1,10)),
}

ICON_COL_WIDTH = 24

# optional Pillow for metadata mode
try:
    from PIL import Image  # type: ignore
except ImportError:
    Image = None

# ────────── icon cache & helpers ──────────────────────────────────────
_ICON_CACHE: Dict[str, QIcon] = {}
_MISSING_ICONS: Set[str] = set()

CATEGORY_MAP = {
    "image.png":   {"jpg","jpeg","png","gif","bmp","tif","tiff","webp"},
    "video.png":   {"mp4","mkv","avi","mov","wmv","flv"},
    "audio.png":   {"mp3","wav","flac","aac","ogg","m4a"},
    "archive.png": {"zip","rar","7z","tar","gz","bz2"},
    "doc.png":     {"pdf","doc","docx","xls","xlsx","ppt","pptx","odt"},
    "code.png":    {"py","js","ts","cpp","c","h","java","cs","sh","rb","go","php"},
}
_EXT_TO_CATEGORY = {ext: cat for cat, exts in CATEGORY_MAP.items() for ext in exts}

def _load_icon_file(name: str) -> QIcon:
    path = ICONS_DIR / name
    if path.exists():
        return QIcon(str(path))
    _MISSING_ICONS.add(name)
    return QIcon()

def _icon_for_path(p: Path) -> QIcon:
    if p.is_dir():
        return _ICON_CACHE.setdefault(
            "__folder__",
            _load_icon_file("folder.png") or QApplication.style().standardIcon(QStyle.SP_DirIcon)
        )
    ext = p.suffix.lstrip(".").lower()
    if ext:
        key = f"ext:{ext}"
        if key not in _ICON_CACHE:
            _ICON_CACHE[key] = _load_icon_file(f"{ext}.png")
        if not _ICON_CACHE[key].isNull():
            return _ICON_CACHE[key]
    cat_file = _EXT_TO_CATEGORY.get(ext)
    if cat_file:
        return _ICON_CACHE.setdefault(cat_file, _load_icon_file(cat_file))
    return _ICON_CACHE.setdefault(
        "__file__",
        _load_icon_file("file.png") or QApplication.style().standardIcon(QStyle.SP_FileIcon)
    )

# ────────── data model utilities ─────────────────────────────────────
@dataclass(slots=True)
class RenameOp:
    src: Path
    tgt: Path

    @property
    def size(self) -> int:
        try:
            return self.src.stat().st_size if self.src.is_file() else 0
        except OSError:
            return 0

    @property
    def mtime(self) -> float:
        try:
            return self.src.stat().st_mtime
        except OSError:
            return 0.0

def _windows_fix(name: str) -> str:
    base, *ext = name.split('.')
    if base.lower() in WIN_RESERVED:
        base += '_'
    base = base.rstrip(' .')
    return base + ('.' + '.'.join(ext) if ext else '')

def sanitise(name: str, bad: Set[str], repl: str | None) -> str:
    txt = ''.join(repl if c in bad else c for c in name) if repl else ''.join(c for c in name if c not in bad)
    txt = re.sub(r'[ \t]+', '_', txt.strip())
    txt = re.sub(r'_+', '_', txt)
    return _windows_fix(txt) or '_'

def _targets(root: Path, rec: bool, files: bool, dirs: bool):
    it = root.rglob('*') if rec else root.iterdir()
    for p in sorted(it, key=lambda x: len(x.parts), reverse=True):
        if p.is_file() and not files: continue
        if p.is_dir() and not dirs: continue
        yield p

def _unique(tgt: Path, taken: set[Path]) -> Path:
    if tgt not in taken and not tgt.exists():
        taken.add(tgt)
        return tgt
    stem, suf, i = tgt.stem, tgt.suffix, 1
    while i < 10000:
        cand = tgt.with_name(f"{stem}_{i}{suf}")
        if cand not in taken and not cand.exists():
            taken.add(cand)
            return cand
        i += 1
    raise RuntimeError("Could not generate unique name")

def _safe_move(src: Path, dst: Path):
    try:
        src.rename(dst)
    except OSError:
        shutil.move(str(src), str(dst))

# ────────── human-readable size helper ───────────────────────────────
def human_readable_size(num_bytes: int) -> str:
    """
    Convert a file size in bytes to a human-readable string,
    scaling from B → KB → MB → GB → TB → PB.
    """
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"

# ────────── photo datetime helper ────────────────────────────────────
def _photo_dt(p: Path) -> datetime | None:
    if Image and p.suffix.lower() in PHOTO_EXTS:
        try:
            exif = Image.open(p).getexif()
            dt   = exif.get(0x9003) or exif.get(0x0132)
            if dt:
                return datetime.strptime(dt, "%Y:%m:%d %H:%M:%S")
        except Exception:
            pass
    try:
        return datetime.fromtimestamp(p.stat().st_mtime)
    except Exception:
        return None

# ────────── rename generators ─────────────────────────────────────────
def generate_standard(root, rec, pf, pd, bad, repl, exts):
    taken, ops = set(), []
    for src in _targets(root, rec, pf, pd):
        if src.is_file() and exts and src.suffix.lower() not in exts: continue
        new = sanitise(src.name, bad, repl)
        if new == src.name or (os.name=="nt" and new.lower()==src.name.lower()): continue
        ops.append(RenameOp(src, _unique(src.with_name(new), taken)))
    return ops

def generate_sequential(root, rec, pf, pd, pre, start, exts):
    taken, ops, n = set(), [], start
    for src in sorted(_targets(root, rec, pf, pd)):
        if src.is_file() and exts and src.suffix.lower() not in exts: continue
        suf = src.suffix if src.is_file() else ""
        ops.append(RenameOp(src, _unique(src.with_name(f"{pre}{n}{suf}"), taken)))
        n += 1
    return ops

def generate_regex(root, rec, pf, pd, pattern, repl, exts):
    rx = re.compile(pattern)
    taken, ops = set(), []
    for src in _targets(root, rec, pf, pd):
        if src.is_file() and exts and src.suffix.lower() not in exts: continue
        new = rx.sub(repl, src.name)
        if new == src.name: continue
        ops.append(RenameOp(src, _unique(src.with_name(new), taken)))
    return ops

def generate_metadata(root, rec, pf, pd, prefix, exts):
    if Image is None:
        raise RuntimeError("Metadata mode requires Pillow – pip install pillow")
    taken, ops = set(), []
    for src in sorted(_targets(root, rec, pf, pd)):
        if src.is_dir() or src.suffix.lower() not in PHOTO_EXTS: continue
        dt = _photo_dt(src)
        if not dt: continue
        ts = dt.strftime("%Y-%m-%d_%H-%M-%S")
        ops.append(RenameOp(src, _unique(src.with_name(f"{prefix}{ts}{src.suffix.lower()}"), taken)))
    return ops

# ────────── threaded workers ──────────────────────────────────────────
class PreviewWorker(QThread):
    finished = Signal(list, str)
    def __init__(self, mode: str, params: Tuple):
        super().__init__()
        self.mode, self.params = mode, params
    def run(self):
        try:
            ops = (generate_standard  if self.mode=="std" else
                   generate_sequential if self.mode=="seq" else
                   generate_regex      if self.mode=="rex" else
                   generate_metadata)(*self.params)
            self.finished.emit(ops, "")
        except Exception as ex:
            self.finished.emit([], str(ex))

class RenameWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(bool, str)
    def __init__(self, ops: List[RenameOp]):
        super().__init__()
        self.ops = ops
    def run(self):
        try:
            for i, op in enumerate(self.ops, 1):
                tmp = op.src.with_name(f".{op.src.name}.swap_tmp")
                _safe_move(op.src, tmp)
                _safe_move(tmp, op.tgt)
                self.progress.emit(i, len(self.ops))
            self.finished.emit(True, "Renaming complete.")
        except Exception as ex:
            self.finished.emit(False, str(ex))

# ────────── proxy & model ────────────────────────────────────────────
class FastFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle = ""
    def setFilterText(self, t: str):
        self._needle = t.lower()
        self.invalidateFilter()
    def filterAcceptsRow(self, row, parent):
        if not self._needle: return True
        sm = self.sourceModel()
        for col in (1, 2):
            val = sm.data(sm.index(row, col, parent), Qt.DisplayRole)
            if val and self._needle in str(val).lower(): return True
        return False

class RenameModel(QAbstractTableModel):
    headers = ("", "Original", "New name", "Type", "Size", "Modified")
    def __init__(self):
        super().__init__()
        self.ops: List[RenameOp] = []
    def rowCount(self, *_): return len(self.ops)
    def columnCount(self, *_): return 6
    def data(self, idx: QModelIndex, role=Qt.DisplayRole):
        if not idx.isValid(): return None
        op, col = self.ops[idx.row()], idx.column()
        if role == Qt.DecorationRole and col == 0:
            return _icon_for_path(op.src)
        if role == Qt.DisplayRole:
            if col == 1: return op.src.name
            if col == 2: return op.tgt.name
            if col == 3: return "Dir" if op.src.is_dir() else op.src.suffix.lstrip(".") or "file"
            if col == 4: return human_readable_size(op.size) if op.size else ""
            if col == 5: return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(op.mtime))
        if role == Qt.TextAlignmentRole and col in (4, 5):
            return Qt.AlignRight | Qt.AlignVCenter
        if role == Qt.ToolTipRole and col == 1:
            return str(op.src)
        return None
    def headerData(self, s, o, r):
        return self.headers[s] if o==Qt.Horizontal and r==Qt.DisplayRole else super().headerData(s,o,r)
    def set_ops(self, ops: List[RenameOp]):
        self.beginResetModel()
        self.ops = ops
        self.endResetModel()

# ────────── settings dialog ─────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, st: QSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(260)
        v = QVBoxLayout(self)
        self.cb_rem = QCheckBox("Remember last folder")
        self.cb_dark = QCheckBox("Use dark theme")
        self.cb_rec = QCheckBox("Default recursive mode")
        for w in (self.cb_rem, self.cb_dark, self.cb_rec):
            v.addWidget(w)
        v.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        self.cb_rem.setChecked(st.value("remember_last", True, bool))
        self.cb_dark.setChecked(st.value("dark_theme", True, bool))
        self.cb_rec.setChecked(st.value("default_recursive", False, bool))

    def accept(self):
        st = QSettings()
        st.setValue("remember_last", self.cb_rem.isChecked())
        st.setValue("dark_theme", self.cb_dark.isChecked())
        st.setValue("default_recursive", self.cb_rec.isChecked())
        super().accept()

# ────────── main window ───────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        QApplication.setOrganizationName(ORG_NAME)
        QApplication.setApplicationName(APP_NAME)
        cfg = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)) / "clean_names.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        self.sts = QSettings(str(cfg), QSettings.IniFormat)

        self.setWindowTitle(f"Clean Names {VERSION}")
        if LOGO_PNG.exists():
            self.setWindowIcon(QIcon(str(LOGO_PNG)))

        self.ops: List[RenameOp] = []
        self.undo: List[RenameOp] = []
        self.preview_worker: PreviewWorker | None = None
        self.rename_worker: RenameWorker | None = None
        self.last_mode = "std"
        self.last_params: Tuple = ()

        self.watcher = QFileSystemWatcher()
        self._watch_timer = QTimer(singleShot=True, interval=500)
        self._watch_timer.timeout.connect(lambda: self._auto_rename(confirm=True))
        self.watcher.directoryChanged.connect(lambda *_: self._watch_timer.start())

        self._build_ui()
        self._restore_splitter()
        self._apply_theme(self.sts.value("dark_theme", True, bool))

    def _build_ui(self):
        # Left panel
        self.splitter = QSplitter(self)
        self.setCentralWidget(self.splitter)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)

        self.le_dir = QLineEdit(readOnly=True)
        lv.addWidget(QLabel("Target folder:"))
        lv.addWidget(self.le_dir)
        lv.addWidget(QPushButton("Browse…", clicked=self._choose_dir))

        self.cb_rec = QCheckBox("Recursive")
        self.cb_files = QCheckBox("Process files", checked=True)
        self.cb_dirs = QCheckBox("Process directories", checked=True)
        self.cb_watch = QCheckBox("Watch folder & auto-rename")
        for w in (self.cb_rec, self.cb_files, self.cb_dirs, self.cb_watch):
            lv.addWidget(w)

        lv.addSpacing(12)
        lv.addWidget(QLabel("Mode:"))
        self.bg_mode = QButtonGroup(self)
        self.rb_std  = QRadioButton("Remove / replace bad chars")
        self.rb_seq  = QRadioButton("Sequential")
        self.rb_rex  = QRadioButton("Regex replace")
        self.rb_meta = QRadioButton("Metadata (photo date)")
        for i, rb in enumerate((self.rb_std, self.rb_seq, self.rb_rex, self.rb_meta)):
            self.bg_mode.addButton(rb, i)
            lv.addWidget(rb)
        self.rb_std.setChecked(True)
        self.bg_mode.idToggled.connect(self._toggle_mode_widgets)

        # Standard mode widgets
        self.le_bad = QLineEdit("".join(sorted(DEFAULT_BAD_CHARS)))
        self.le_rep = QLineEdit("_"); self.le_rep.setMaximumWidth(40)
        lv.addWidget(QLabel("Bad characters:")); lv.addWidget(self.le_bad)
        rep_row = QHBoxLayout()
        rep_row.addWidget(QLabel("Replace with:")); rep_row.addWidget(self.le_rep); rep_row.addStretch()
        lv.addLayout(rep_row)

        # Sequential mode widgets
        seq_row = QHBoxLayout()
        seq_row.addWidget(QLabel("Prefix:")); self.le_pre = QLineEdit("item"); seq_row.addWidget(self.le_pre)
        seq_row.addWidget(QLabel("Start #:")); self.spin_num = QSpinBox(maximum=10_000_000, value=1)
        self.spin_num.setMaximumWidth(90); seq_row.addWidget(self.spin_num); seq_row.addStretch()
        lv.addSpacing(6); lv.addLayout(seq_row)

        # Regex mode widgets
        self.le_pattern = QLineEdit(); self.le_repl = QLineEdit()
        lv.addWidget(QLabel("Regex pattern:")); lv.addWidget(self.le_pattern)
        lv.addWidget(QLabel("Regex replace:")); lv.addWidget(self.le_repl)

        # Metadata mode widget
        self.le_meta_pre = QLineEdit()
        lv.addWidget(QLabel("Metadata prefix (optional):")); lv.addWidget(self.le_meta_pre)

        # Extensions list
        lv.addSpacing(10); lv.addWidget(QLabel("Include extensions:"))
        self.lst_ext = QListWidget(); self.lst_ext.setMaximumHeight(150); self.lst_ext.setSelectionMode(QListWidget.NoSelection)
        lv.addWidget(self.lst_ext)
        add_row = QHBoxLayout()
        self.le_add_ext = QLineEdit(); self.le_add_ext.setPlaceholderText(".log")
        add_row.addWidget(self.le_add_ext); add_row.addWidget(QPushButton("Add", clicked=self._add_ext))
        lv.addLayout(add_row)

        lv.addStretch(1)
        btn_row = QHBoxLayout()
        self.btn_preview = QPushButton("Preview", clicked=self._start_preview)
        self.btn_rename  = QPushButton("Rename", clicked=self._rename)
        btn_row.addWidget(self.btn_preview); btn_row.addWidget(self.btn_rename); lv.addLayout(btn_row)

        self.splitter.addWidget(left)

        # Right panel
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 4, 4, 4)

        tb = QToolBar(movable=False); self.addToolBar(tb)
        tb.addAction(QIcon(str(OPEN_PNG)), "Open…", self._choose_dir)
        tb.addAction(QIcon(str(UNDO_PNG)), "Undo", self._undo_last)
        tb.addAction(QIcon(str(SET_PNG)),  "Prefs", self._open_settings)
        tb.addAction(QIcon(str(HELP_PNG)), "Help", self._open_help)
        tb.addAction(QIcon(str(INFO_PNG)), "About", self._about)

        filt = QHBoxLayout(); filt.addWidget(QLabel("Filter:")); self.le_filter = QLineEdit(); filt.addWidget(self.le_filter,1); rv.addLayout(filt)

        self.model = RenameModel()
        self.proxy = FastFilterProxy()
        self.proxy.setSourceModel(self.model)

        self.tbl = QTableView()
        self.tbl.setModel(self.proxy)
        self.tbl.setSortingEnabled(True)
        self.tbl.setIconSize(QSize(16, 16))

        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setMinimumHeight(self.fontMetrics().height() + 16)
        hdr.setStyleSheet("QHeaderView::section{background:#404048;padding:4px}")
        self.tbl.setSelectionBehavior(QTableView.SelectRows)
        rv.addWidget(self.tbl, 1)

        self.splitter.addWidget(right)

        sb = QStatusBar(); self.pg = QProgressBar(maximumWidth=220, visible=False); sb.addPermanentWidget(self.pg); self.setStatusBar(sb)

        # Debounced filter
        self._filter_timer = QTimer(singleShot=True, interval=160)
        self._filter_timer.timeout.connect(lambda: self.proxy.setFilterText(self.le_filter.text()))
        self.le_filter.textChanged.connect(lambda: self._filter_timer.start())

        self._toggle_mode_widgets()
        self._load_settings()
        QTimer.singleShot(0, self._apply_header_state)

        # Show missing icon debug
        if _MISSING_ICONS:
            self.statusBar().showMessage("Missing icons: " + ", ".join(sorted(_MISSING_ICONS)), 5000)

    def _toggle_mode_widgets(self):
        mode = self.bg_mode.checkedId()
        for idx, widget in (
            (0, self.le_bad), (0, self.le_rep),
            (1, self.le_pre), (1, self.spin_num),
            (2, self.le_pattern), (2, self.le_repl),
            (3, self.le_meta_pre),
        ):
            widget.setEnabled(mode == idx)

    def _sel_ext(self) -> Set[str] | None:
        exts = {self.lst_ext.item(i).text()
                for i in range(self.lst_ext.count())
                if self.lst_ext.item(i).checkState() == Qt.Checked}
        return exts or None

    def _add_ext(self):
        t = self.le_add_ext.text().strip().lower()
        if not t: return
        if not t.startswith("."): t = "." + t
        for i in range(self.lst_ext.count()):
            if self.lst_ext.item(i).text() == t:
                self.lst_ext.item(i).setCheckState(Qt.Checked)
                self.le_add_ext.clear()
                return
        it = QListWidgetItem(t)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked)
        self.lst_ext.addItem(it)
        self.le_add_ext.clear()

    def _choose_dir(self):
        p = QFileDialog.getExistingDirectory(self, "Choose folder", self.sts.value("last_folder", ""))
        if p:
            self.le_dir.setText(p)
            self.sts.setValue("last_folder", p)
            # guard removePaths
            dirs = self.watcher.directories()
            if dirs:
                self.watcher.removePaths(dirs)
            if self.cb_watch.isChecked():
                self.watcher.addPath(p)

    def _open_settings(self):
        dlg = SettingsDialog(self.sts, self)
        if dlg.exec():
            self._apply_theme(self.sts.value("dark_theme", True, bool))

    def _start_preview(self, from_watch=False):
        if not self.le_dir.text():
            QMessageBox.warning(self, "No folder", "Choose a target folder first.")
            return
        self.btn_preview.setEnabled(False)
        self.btn_rename.setEnabled(False)
        self.pg.setRange(0, 0); self.pg.setVisible(True)

        root = Path(self.le_dir.text())
        rec = self.cb_rec.isChecked(); f_ok = self.cb_files.isChecked(); d_ok = self.cb_dirs.isChecked()
        exts = self._sel_ext()
        mode_id = self.bg_mode.checkedId()
        if mode_id == 0:
            bad = set(self.le_bad.text()) or DEFAULT_BAD_CHARS
            repl = self.le_rep.text() or None
            if repl and len(repl) != 1:
                self._busy_done()
                QMessageBox.warning(self, "Invalid replacement", "Replacement must be exactly one character.")
                return
            mode, params = "std", (root, rec, f_ok, d_ok, bad, repl, exts)
        elif mode_id == 1:
            mode, params = "seq", (root, rec, f_ok, d_ok, self.le_pre.text() or "item", self.spin_num.value(), exts)
        elif mode_id == 2:
            mode, params = "rex", (root, rec, f_ok, d_ok, self.le_pattern.text(), self.le_repl.text(), exts)
        else:
            mode, params = "meta", (root, rec, f_ok, d_ok, self.le_meta_pre.text(), exts)

        self.last_mode, self.last_params = mode, params
        self.preview_worker = PreviewWorker(mode, params)
        self.preview_worker.finished.connect(lambda ops, err: self._preview_finished(ops, err, from_watch))
        self.preview_worker.start()

    def _preview_finished(self, ops: List[RenameOp], err: str, from_watch: bool = False):
        self._busy_done()
        if err:
            if not from_watch:
                QMessageBox.critical(self, "Error", err)
            return
        if from_watch:
            self.ops = ops
            if ops:
                self._auto_rename(confirm=False)
            return
        self.ops = ops
        self.model.set_ops(ops)
        self.statusBar().showMessage(f"{len(ops)} operation(s) ready.")
        if not ops:
            QMessageBox.information(self, "Nothing to rename", "No changes required.")

    def _busy_done(self):
        self.pg.setVisible(False)
        self.btn_preview.setEnabled(True)
        self.btn_rename.setEnabled(True)

    def _rename(self):
        if not self.ops:
            QMessageBox.information(self, "Nothing to do", "Run Preview first.")
            return
        if QMessageBox.question(self, "Confirm", f"Proceed with renaming {len(self.ops)} item(s)?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.pg.setRange(0, len(self.ops)); self.pg.setValue(0); self.pg.setVisible(True)
        self.rename_worker = RenameWorker(self.ops)
        self.rename_worker.progress.connect(lambda i, _: self.pg.setValue(i))
        self.rename_worker.finished.connect(self._rename_finished)
        self.rename_worker.start()

    def _rename_finished(self, ok: bool, msg: str):
        self.pg.setVisible(False)
        if ok:
            self._log_undo_batch(self.ops)
            self.undo = self.ops.copy()
            self.ops.clear()
            self.model.set_ops([])
            self.statusBar().showMessage(msg, 3000)
        else:
            QMessageBox.critical(self, "Rename failed", msg)

    def _log_undo_batch(self, ops: List[RenameOp]):
        path = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)) / "last_batch.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps([[str(o.src), str(o.tgt)] for o in ops]), encoding="utf-8")
        except Exception:
            pass

    def _undo_last(self):
        if not self.undo and not self._load_persisted_undo():
            return
        if QMessageBox.question(self, "Undo", f"Revert last batch ({len(self.undo)} item(s))?",
                                 QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        errs = []
        for op in reversed(self.undo):
            try:
                _safe_move(op.tgt, op.src)
            except Exception as ex:
                errs.append(str(ex))
        self.undo.clear()
        QMessageBox.information(self, "Undo", "Undo complete." if not errs else "\n".join(errs))

    def _load_persisted_undo(self) -> bool:
        path = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)) / "last_batch.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.undo = [RenameOp(Path(tgt), Path(src)) for src, tgt in data]
            path.unlink()
            return True
        except Exception:
            return False

    def _update_watcher(self):
        dirs = self.watcher.directories()
        if dirs:
            self.watcher.removePaths(dirs)
        if self.cb_watch.isChecked() and self.le_dir.text():
            self.watcher.addPath(self.le_dir.text())

    def _auto_rename(self, confirm: bool = True):
        if confirm and QMessageBox.question(self, "Auto-rename",
                                            "Folder changed – apply last rules?",
                                            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._start_preview(from_watch=True)
        if confirm:
            self.statusBar().showMessage("Auto-rename finished.", 3000)

    def _apply_header_state(self):
        hdr = self.tbl.horizontalHeader()
        data = self.sts.value("header_state", "")
        if data:
            hdr.restoreState(QByteArray.fromBase64(data.encode()))
        else:
            self._equalize_columns()

    def _equalize_columns(self):
        hdr = self.tbl.horizontalHeader()
        total = self.tbl.viewport().width() or self.tbl.width() or 900
        cols = self.model.columnCount() - 1
        width = (total - ICON_COL_WIDTH) // cols
        hdr.resizeSection(0, ICON_COL_WIDTH)
        for i in range(1, self.model.columnCount()):
            hdr.resizeSection(i, width)

    def _save_header_state(self):
        state = self.tbl.horizontalHeader().saveState().toBase64()
        self.sts.setValue("header_state", bytes(state).decode())

    def _restore_splitter(self):
        js = self.sts.value("splitter_sizes", "")
        try:
            if js:
                self.splitter.setSizes(list(json.loads(js)))
                return
        except Exception:
            pass
        self.splitter.setSizes([340, 860])

    def _save_splitter(self):
        self.sts.setValue("splitter_sizes", json.dumps(self.splitter.sizes()))

    def _apply_theme(self, dark: bool):
        QApplication.setStyle("Fusion")
        accent = QColor("#2080ff")
        pal = QPalette()
        if dark:
            pal.setColor(QPalette.Window, QColor(37, 37, 43))
            pal.setColor(QPalette.Base, QColor(27, 27, 33))
            pal.setColor(QPalette.AlternateBase, QColor(47, 47, 55))
            pal.setColor(QPalette.Text, Qt.white)
            pal.setColor(QPalette.Button, QColor(55, 55, 65))
            pal.setColor(QPalette.ButtonText, Qt.white)
            pal.setColor(QPalette.Highlight, accent)
            pal.setColor(QPalette.HighlightedText, Qt.white)
            pal.setColor(QPalette.WindowText, Qt.white)
        QApplication.setPalette(pal)

        css = f"""
        QPushButton {{
            background:{accent.name()}; color:#fff; border:none;
            padding:5px 10px; border-radius:4px;
        }}
        QPushButton:hover  {{ background:{accent.lighter(110).name()}; }}
        QPushButton:pressed{{ background:{accent.darker(120).name()}; }}
        QPushButton:disabled{{ background:#555; color:#888; }}

        QListView::indicator {{
            width:14px; height:14px; border:1px solid {accent.name()};
        }}
        QListView::indicator:checked {{
            background:{accent.name()};
            image:url("{CHECK_PNG.as_posix()}");
        }}
        QListView::indicator:unchecked {{ background:transparent; }}

        QLineEdit:disabled, QSpinBox:disabled, QListWidget:disabled {{
            color:#888; background:#333;
        }}
        QHeaderView::section {{
            background:#404048;  /* header contrast */
        }}
        QRadioButton:disabled, QCheckBox:disabled {{ color:#888; }}
        """
        QApplication.instance().setStyleSheet(css)

    def _load_settings(self):
        if self.sts.value("remember_last", True, bool):
            self.le_dir.setText(self.sts.value("last_folder", ""))
        self.cb_rec.setChecked(self.sts.value("default_recursive", False, bool))
        self.le_filter.setText(self.sts.value("filter_text", ""))

        self.lst_ext.clear()
        try:
            items = json.loads(self.sts.value("ext_items", "[]"))
            for text, checked in items or [[e, False] for e in DEFAULT_EXTS]:
                it = QListWidgetItem(text)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                self.lst_ext.addItem(it)
        except Exception:
            for e in DEFAULT_EXTS:
                it = QListWidgetItem(e)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked)
                self.lst_ext.addItem(it)

        self.cb_watch.setChecked(False)
        # guard removePaths
        dirs = self.watcher.directories()
        if dirs:
            self.watcher.removePaths(dirs)

    def _open_help(self):
        if HELP_HTML.exists():
            webbrowser.open(HELP_HTML.resolve().as_uri())
        else:
            QMessageBox.warning(self, "Help missing", str(HELP_HTML))

    def _about(self):
        QMessageBox.about(
            self,
            "About",
            f"<b>Clean Names {VERSION}</b><br>"
            "Dark-themed, open-source batch renamer.",
        )

    def closeEvent(self, e):
        self._save_header_state()
        self._save_splitter()
        self.sts.setValue("filter_text", self.le_filter.text())
        items = [
            [self.lst_ext.item(i).text(), self.lst_ext.item(i).checkState() == Qt.Checked]
            for i in range(self.lst_ext.count())
        ]
        self.sts.setValue("ext_items", json.dumps(items))
        super().closeEvent(e)

# ────────── entry point ─────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    if LOGO_PNG.exists():
        app.setWindowIcon(QIcon(str(LOGO_PNG)))
    win = MainWindow()
    win.show()
    QTimer.singleShot(0, win.showMaximized)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
