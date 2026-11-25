# CLAUDE.md

NeXus/HDF5 data viewer for the Diamond Light Source Magnetic Materials Group (beamlines i06, i10, i16, i21…).
There are two GUIs in one package (`mmg-tk-dataviewer`):

| Package | Command | Framework |
|---|---|---|
| `src/mmg_tk_dataviewer/` | `dataviewer` | Tkinter, the original |
| `src/mmg_qt_dataviewer/` | `dataviewer-qt` | PySide6, a simpler and more modern rewrite of the same windows |

Both rely on **mmg_toolbox** for file reading, fitting, XAS/XMCD processing, script templates and beamline/env helpers. They also rely on **hdfmap** (`NexusMap`) to resolve names in NeXus files. Keep the GUI code thin and put data logic in mmg_toolbox.

## Commands

```sh
uv run dataviewer-qt [beamline | folder | file.nxs]   # Qt viewer
uv run dataviewer   [beamline | folder | file.nxs]    # tk viewer
uv run --extra dev pytest                             # all tests
uv run --extra dev pytest tests/test_qt_dataviewer.py -rs
```

- `mmg-toolbox` is an **editable path source at `../mmg_toolbox`** (see `[tool.uv.sources]`), so a sibling checkout must exist. Commit `uv.lock` whenever dependencies change.
- **PySide6 is capped `<6.10`.** Wheels from 6.10 onwards need glibc 2.34, but the Diamond workstations run RHEL 8 with glibc 2.28. Don't raise the cap.
- Users have **no admin rights**, so they can't `apt-get`. Fixes must work with pip/uv wheels alone.

## Tests

- `tests/test_qt_dataviewer.py`:
  - Runs off-screen with `QT_QPA_PLATFORM=offscreen`, set by default in the test.
  - Writes its own small NeXus files with the `make_scan` fixture.
  - Uses a config with `roi=[]` and a simple `metadata_string`, because the beamline metadata strings fail on synthetic files.
  - Skips via `pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)` if Qt's system libraries (e.g. libGL) are missing.
- `tests/test_dataviewer.py` (tk): most tests need `/dls` data and skip off-site.
- When you add a Qt window, extend `test_other_windows` or add a test that constructs it.

## Qt package layout (`src/mmg_qt_dataviewer/`)

- `cli.py`: `run(*args)` opens TitleWindow for a beamline, DataViewer for a folder, or NexusViewer for a file. It applies the saved theme first.
- `config.py`:
  - `C` holds the key names. Also provides `get_config(beamline)`, `save_config` and `BEAMLINE_CONFIG`.
  - **It shares the config file with the tk app** (`$TMPDIR/mmg_config_{user}.json`), so new keys must not break tk.
- `style.py`: theming and layout helpers. Use these rather than hand-rolled styling.
  - `THEMES` holds the light/dark colours; `CURRENT` is the active palette. `STYLESHEET` is QSS with `{}` placeholders.
  - `apply_theme(app, theme)` sets Fusion, the palette, the QSS and matplotlib `rcParams`, and restyles open `PlotCanvas` widgets.
  - `icon_files()` generates SVG arrow/check icons in a temp dir. QSS CSS-triangles render as grey blocks, so don't use them.
  - Helpers:
    - `card(*widgets, layout=None, title='')`
    - `form(*rows)`
    - `row(*widgets, stretch=None)`, where `None` inserts a stretch
    - `grid(widgets, columns)`
    - `scrollable(w)`
    - `heading(text, scale)`
    - `fit_to_screen(window, w, h)`, which caps at 92% of the available screen and centres the window
- `common.py`:
  - `get_app(theme)` sets `HighDpiScaleFactorRoundingPolicy.PassThrough` *before* creating the QApplication.
  - `show_window` keeps references in `WINDOWS` and starts the event loop on the first window.
  - `add_menus(window, menus, config)` adds the View › Theme, Config and Help menus.
  - `PlotCanvas` (QFrame, objectName `plot`): a matplotlib canvas with a compact toolbar.
  - Also `button(text, fn, parent, primary)`, `tool_button`, `monospace()`, `run_safely`, `show_error`, the file dialogs, terminal/jupyter launchers and `TextWindow`.
- `scan_list.py`: `ScanList` is the folder → scan tree.
  - Emits `selectionChanged(list)`.
  - Fills metadata incrementally with a QTimer and polls for new files every 5 s.
  - The right-click menu opens other windows.
- `plots.py`:
  - `LinePlot(config, axis_list=False)` has X/Y combos and Options/Fit/Analyse menus. With `axis_list=True` it shows the `y_list` side list, which is the Qt equivalent of tk `NexusMultiAxisPlot._axis_listbox`.
  - `ImagePlot` has the detector combo, a frame slider and Draw ROI.
  - Also `PlotWindow`, `open_plot_window` and `open_image_window`.
- `data_viewer.py`: the main window.
  - The left side holds the Scans card and a DetailsPanel with Details/Console/Notebooks tabs. The right side is a plots splitter.
  - `resizeEvent` puts the plots side by side when width ≥ 1.8 × height and width ≥ 1800.
- The other windows:
  - `nexus_viewer.py`: tree, HdfMap and lazily loaded string tabs, plus evaluate-expression.
  - `title_window.py`, `file_browser.py`, `multi_scan.py` (`ScanRange`) and `peak_fit.py`.
  - `xmcd/`: the XMCD Visualiser package.
    - `analysis.py` has **no Qt**: processing `Step`s and `apply_chain`, `find_pairs`, `Pair`, `Result` (averages, dichroism, sum rules) and `to_script` / `to_notebook` code generation. Test analysis changes here first.
    - `draw.py` holds plot functions `draw_*(axes, ...)`, so the same plot can be drawn in a pop-out via `common.popout(title, draw)`.
    - `scans.py` (scan browser with preview, pair list), `chain_editor.py`, `grid.py` (pair grid with include checkboxes), `results.py` (Average, Sum rules, Series tabs) and `window.py`.
    - Load XAS files one at a time with `analysis.load_scan`. `Experiment.load_xas` defaults to `match_metadata=True` and silently adds or drops scans.
    - The **DLS loader** checkbox is on by default, which is what real beamline files need. The synthetic files in the tests and `docs/generate_qt_ui_images.py` can't be read that way, so those untick it straight after creating the window, before the scans load.
    - Pairing: **Auto-pair** uses the scans selected in the Scans table, or all loaded scans if fewer than two are selected. **Add selected pair** needs exactly two selected scans. Both are also in the Scans table's right-click menu (`ScanBrowser.pairRequested` / `autoPairRequested`). Keep the tooltips and the hint label in `PairList` accurate if pairing changes, because users found pairing unclear.
    - The detection-mode combo is filled whenever the pairs change (`_update_modes`), not only after every scan has loaded. Real folders such as `/dls/science/groups/das/ExampleData/i10-1/nt42193-1` hold hundreds of scans and take a long time to load.
    - The Average tab's top two plots show every scan of each polarisation (not their average). The averages are overlaid in the third plot.
    - Panel widths: the left scroll area's minimum width comes from its contents' `minimumSizeHint()`, and the right card's from the tabs' minimum width. Hard-coded widths clipped buttons at 1280×720 and 1366×768.
  - `editors.py` (Python editor, log viewer), `config_editor.py`, `visits.py` and `processing.py` (script/notebook templates from mmg_toolbox).

## Qt conventions and gotchas

- **Keep the code simple.** Prefer the helpers in `style.py`/`common.py`, keyword-argument widget construction (`QLineEdit(placeholderText=...)`) and small classes. Copy behaviour from the tk widgets rather than inventing new features.
- Never call `matplotlib.use('QtAgg')`, because it raises ImportError when headless. Import `FigureCanvasQTAgg` directly.
- Don't hard-code plot colours like black. Use `CURRENT['text']` or `CURRENT['muted']` so dark mode works.
- Don't give toolbars `background: transparent` in QSS. matplotlib's icon engine then thinks it is in dark mode and draws invisible icons.
- `widget.isVisible()` is False until the window is shown, so keep your own flag (e.g. `self.axis_list`). Use `setHidden()` only after a widget has a parent. Showing a parentless widget opens a separate window.
- The y-axis names are `map.scannables` plus `f"{roi}_total"` for config ROIs only. Don't list every hdfmap `*_total` name.
- A word-wrapped `QLabel` isn't counted properly in its layout's minimum height, so a panel squeezed to its minimum (e.g. inside a `QSplitter`) lets widgets overlap. Set the minimum from the wrapped height in `resizeEvent`: `self.setMinimumHeight(self.layout().minimumHeightForWidth(self.width()))`, as `xmcd.scans.PairList` does.
- Check layouts at small and large sizes, from 1280×720 and 1366×768 up to 2560×1440 and 3440×1440, in light and dark themes.

## tk package layout (`src/mmg_tk_dataviewer/`)

- `apps/` holds the top-level windows. `widgets/` holds reusable frames (`nexus_plot.py`, `folder_treeview.py`, `multi_scan_analysis.py`…). `misc/` holds config, styles, jupyter, logging and screen size. `xmcd_visualiser/` is the XMCD app.
- Import tk modules locally (`mmg_tk_dataviewer...`), **not** from `mmg_toolbox.tkguis`.
- `docs/windows.md` describes every tk window, and `docs/generate_ui_images.py` generates its images.

## Git / GitHub

- Repo: `DiamondLightSource/mmg_tk_dataviewer`, default branch `main`. Work on `claude/<topic>` branches and open PRs with `gh`.
- `docs/qt_screenshots/` is a local scratch folder of screenshots. Don't commit it.
- Inside claude-sandbox, push with plain `git push`. If auth fails, ask the user to run `claude-sandbox gh-auth` in the outer shell. The token needs Contents read/write.
