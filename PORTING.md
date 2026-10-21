# Porting conventions (STAMP 2.1.3 -> Python 3.12 / PyQt6 / matplotlib 3.x)

Shared rules for every file under `stamp/`. Keep diffs minimal and semantics identical to
upstream; this is a port, not a rewrite. Keep upstream's tab indentation, file names, class
names (PluginManager loads `<file>.py` and instantiates the class named `<file>`), GPL headers,
`.ui` files and icons. Never add features. Mark deliberate shortcuts with a `ponytail:` comment.

Layout: `stamp/` is the upstream root (`stamp/stamp/` is the Python package). Tests live in
`tests/` at the repository root and import with `stamp/` on `sys.path` (see `tests/conftest.py`).
Run tests with `uv run pytest tests/<file>`; GUI tests need `QT_QPA_PLATFORM=offscreen`.

## Python 2 -> 3 (a mechanical 2to3 pass is already applied on main)
- Audit every `/` whose result is used as an index, range bound, count, or pixel size; use `//`
  where upstream relied on integer division. This is the main silent-correctness risk.
- `cmp`-style sorts -> `key=`; `dict.keys()[i]` -> `list(d)[i]`; `map/filter/zip` return
  iterators (2to3 wrapped some in `list()`; check the rest); `round()` returns int.
- Text files: `open(path)` (text mode, universal newlines). `'U'` mode is already removed.
- `string.strip/lower/...` module functions -> `str` methods; `unicode` -> `str`.
- Remove `imp` (use `getattr(sys, 'frozen', False)`), `apply(f, args)` -> `f(*args)`.
- numpy 2 / scipy 1.18: `scipy.array/arange` -> `numpy`; `scipy.random.random_integers(lo, hi)`
  -> `numpy.random.randint(lo, hi + 1)` (keep inclusive upper bound); `scipy.stats.mstats`,
  `scipy.stats.distributions` still exist; check every scipy call against current docs.

## PyQt4 -> PyQt6
- `from PyQt6 import QtCore, QtGui, QtWidgets`. Widgets (`QDialog`, `QMainWindow`, `QLabel`,
  `QMessageBox`, `QFileDialog`, `QSizePolicy`, `QTableWidgetItem`, `QColorDialog`, ...) live in
  `QtWidgets`; `QColor`, `QIcon`, `QPixmap`, `QFont`, `QAction`, `QShortcut`, `QPalette` in `QtGui`.
- Signals: `self.connect(obj, QtCore.SIGNAL('sig(args)'), slot)` -> `obj.sig.connect(slot)`.
  Custom signals become class attributes: `legendItemChanged = QtCore.pyqtSignal()` and
  `self.legendItemChanged.emit()`. Overloaded signals: `obj.sig[int].connect(slot)` when needed
  (e.g. `currentIndexChanged[str]` no longer exists; use `currentTextChanged`).
- Enums are fully scoped: `QtCore.Qt.AlignmentFlag.AlignLeft`, `QtCore.Qt.ItemDataRole.DisplayRole`,
  `QtCore.Qt.CheckState.Checked`, `QtCore.Qt.DockWidgetArea.RightDockWidgetArea`,
  `QtWidgets.QSizePolicy.Policy.Fixed`, `QtWidgets.QMessageBox.StandardButton.Ok`,
  `QtWidgets.QDialog.DialogCode.Accepted`, `QtGui.QIcon.Mode.Normal`, `QtGui.QIcon.State.Off`,
  `QtWidgets.QHeaderView.ResizeMode.Stretch`, `QtWidgets.QAbstractItemView.SelectionMode...`.
- `exec_()` -> `exec()`. `QtGui.QDesktopWidget().screenGeometry()` ->
  `QtWidgets.QApplication.primaryScreen().availableGeometry()`.
- `QString`/`QVariant` are gone: `str(widget.text())` stays valid; `QtCore.QString(x)` -> `str(x)`;
  `v.toPyObject()`/`toString()` -> the value itself. `QStringList` -> `list[str]`.
- QSettings: `settings.value(key, default).toDouble()[0]` -> `settings.value(key, default, type=float)`;
  `toInt()[0]` -> `type=int`; `toBool()` -> `type=bool`; `toString()` -> `type=str`.
  Values written by this port must round-trip (QSettings stores strings on macOS plists).
- `QFileDialog.getOpenFileName/getSaveFileName` return `(path, selectedFilter)`; unpack the path.
- `QtWidgets.QApplication.setStyle('Windows')` with fallback `'Fusion'`; in-window menu bar via
  `self.menuBar().setNativeMenuBar(False)` (both only in `stamp/stamp/STAMP.py`).
- Generated UI: regenerate `*UI.py` from the `.ui` with `uv run pyuic6 x.ui -o xUI.py` (verified to
  work for all 34 files) rather than hand-editing. Keep the `from . import STAMP_rc`-style import
  that `pyuic6` emits only if the module exists at that path; `mainUI.py` must import
  `stamp.STAMP_rc`. Resources: convert `STAMP_rc.py` literals to `bytes` (`b"..."`) and keep
  `QtCore.qRegisterResourceData(0x01, ...)`, which PyQt6 still provides.

## matplotlib 1.4 -> 3.11
- `from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas`.
- `bbox.inverse_transformed(t)` -> `bbox.transformed(t.inverted())`.
- `self.get_renderer()` on a canvas -> `self.figure.canvas.get_renderer()` (Agg canvas has it).
- `mpl_toolkits.axes_grid` -> `mpl_toolkits.axes_grid1`; `pylab` -> explicit `numpy`/`pyplot`.
- `spines.iteritems()` -> `items()`; `cm.get_cmap(name)` -> `matplotlib.colormaps[name]`;
  `ax.set_axis_bgcolor` -> `set_facecolor`; `errorbar(..., capsize=)` ok; integer `legend(loc=n)` ok.
- `FigureCanvas.setSizePolicy(self, QtWidgets.QSizePolicy.Policy.Fixed, ...)`.
- Numeric output (p-values, effect sizes, CIs) must not change; plot code may only change API calls.

## Verification per worker
- Own pytest file(s) under `tests/`, headless (`QT_QPA_PLATFORM=offscreen`), using the example
  data under `stamp/examples/` (Enterotypes has metadata and multiple groups).
- `uv run python -m compileall -q stamp` clean; `grep -rn PyQt4 <owned paths>` empty.
- Report exact commands run and anything unverified.
