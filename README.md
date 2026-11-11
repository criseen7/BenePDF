# Bene PDF

**English** | [Español](README.es.md)

Desktop application to view, organize, and edit PDF documents without uploading anything to external services.

The project is under construction. Iterations 1 to 3 cover opening, viewing, navigation, zoom, view rotation, thumbnails, in-memory editing of text and images, permanent redaction, and safe export to a new file. Iteration 4 fixes resizing and export on rotated or cropped pages, embeds fonts, and warns about text that does not fit. Iteration 5 adds actionable export errors, keyboard accessibility, tests with 100-page documents, PyInstaller packaging, and continuous integration. Iteration 6 adds text search, document information, page rotation/reordering/deletion/extraction, and replacement of embedded images. Iteration 7 adds freehand drawing with configurable color and thickness, selectable and resizable vector strokes. The integrity review from the roadmap now also removes annotations and form fields that intersect a redaction, and adds `Ctrl`+wheel zoom and an unsaved-changes marker in the window title.

> The application interface and the detailed project documentation are currently in Spanish. This guide translates the interface labels into English for readability; the [Spanish README](README.es.md) shows them as they appear in the application.

- Requirements and acceptance criteria: [docs/requirements.md](docs/requirements.md)
- Main roadmap: [BenePDF_Plan_Mejoras_Evolucion_Correcciones.md](BenePDF_Plan_Mejoras_Evolucion_Correcciones.md)
- Work plan, status, and iteration log: [PLAN.md](PLAN.md)
- Architecture decisions: [docs/decisions/](docs/decisions/)
- Changes by version: [CHANGELOG.md](CHANGELOG.md)

## Requirements

- Windows 10/11 (development and runtime) with Python 3.12
- No Internet connection required to use the application

## Installation on Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell blocks environment activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Usage guide

### Open a PDF

1. Activate the environment and start the application with `bene`.
2. Click **Open…** on the toolbar or press `Ctrl+O`.
3. You can also drag a PDF file from File Explorer and drop it onto the window.
4. From a terminal you can open a document directly:

   ```powershell
   bene "C:\path\to\document.pdf"
   ```

When opened, Bene PDF shows the first page fitted to the window. If the PDF is encrypted, it asks for the password; up to three attempts are allowed, and the password is kept only in memory.

### Navigate the document

- Type the page number into the selector on the top bar and press `Enter`.
- Use the **◀** and **▶** buttons, or the `PgUp` and `PgDn` keys, to go to the previous or next page.
- Click a thumbnail in the **Pages** panel to jump directly to that page. Thumbnails are generated in the background, and the current page is highlighted.
- The status bar shows the current page, the total, the rough classification of the page (text, scanned image, graphic content, or empty page), its dimensions in points, and the applied zoom.

Rendering happens in the background: while a page is being prepared you will see **Rendering…** and, when it finishes, **Ready**. Pages already visited are kept in memory so going back is immediate.

### Search text

1. Click **Search…** (`Ctrl+F`) or use Edit → Search…
2. Type the text and press `Enter` or **Search**. The search scans the whole document in the background.
3. Matches appear in the **Search** panel with their page and a snippet. Selecting one jumps to its page and highlights it.
4. Use **Next** and **Previous**, or `F3` and `Shift+F3`, to move through the matches.

Search is case-insensitive and does not include OCR: scanned documents without recognizable text will return no results. If a match is on a page removed from the working copy, it remains in the list, but a warning says it will not be exported.

### Pages

Page operations apply to the working copy and only change the file on export. The page selector and the status bar use the output order; if you have deleted pages, the status bar also shows the original page number.

- **Rotate page 90°** (`Ctrl+Alt+R`): adds an extra rotation to the visible page. It is different from **Rotate view**: page rotation is saved in the exported file.
- **Move page up / down** (`Ctrl+Alt+↑` / `Ctrl+Alt+↓`): changes the output order.
- **Delete page…** (`Ctrl+Alt+Delete`): asks for confirmation and warns if the page has added objects, which will be omitted from the export. You can undo it before exporting.
- **Extract pages…** (`Ctrl+Alt+E`): writes a selection such as `1-3, 5` to a new file. It does not alter the session, the history, or the unsaved-changes state.

### Replace an embedded image

1. Open **Page → Replace image…**.
2. Choose one of the images detected on the visible page and click **Choose replacement image…** to select a PNG or JPEG.
3. Confirm with **Replace**. The replacement is applied only on export.

If the image is shared across several pages, the dialog warns that it will change on all of them. Inline images, images inside forms, and those that the PDF does not identify with a reliable `xref` cannot be replaced and are omitted from the list.

### Document information

**File → Document information…** (`Ctrl+Alt+I`) shows the name and path, the page count, the pages that will be exported, the file size, the dimensions of the current page, the protection, and the available metadata (title, author, dates, etc.). The data comes from the PDF itself and may be missing or incorrect.

### Edit the document

Changes are kept **only in memory** during the session: the original PDF is never modified. When you are done, export them to a new file.

1. **Select region** (`Ctrl+Shift+R`): drag over the page to mark a rectangle. The status bar shows its coordinates and size in PDF points.
2. **Redact region** (`Ctrl+Shift+X`): drag over the content you want to remove. Confirmation is requested because, on export, the underlying content is permanently erased from the new file. The region is shown in black and can be moved, resized, or deleted like any other object before export.
3. **Add text** (`Ctrl+T`): enter the content and choose the font, size, color, and alignment. If a region is selected, the text fills that region; otherwise, the tool remains active and the text is placed with a click. You can redact an area and type the corrected text over it in the same step. The Helvetica, Times-Roman, and Courier fonts are embedded in the PDF, so they preserve the euro sign, accents, and Latin alphabets; if the text does not fit its region or uses characters that the font does not support, the object is marked in red and export is blocked with a warning that indicates the page and the missing space.
4. **Insert image** (`Ctrl+I`): supports PNG and JPEG up to 20 MB. Like text, it uses the selected region or the next click. The image keeps its original aspect ratio.
5. **Draw** (`Ctrl+Shift+D`): drag over the page to draw freehand. The **Drawing** toolbar sets the color and the thickness from 0.5 to 50 pt. The tool stays active after each stroke so you can draw several in a row; switch to **Select** or another tool to stop. Strokes are saved as vectors and can be selected, moved, resized, deleted, undone, and redone like any other object. Resizing changes the shape but keeps the thickness. Drawing over text only covers it visually: use **Redact region** to remove the underlying content permanently.
6. **Move and resize**: with the **Select** tool (`Ctrl+Shift+V`), click an object to select it. With the object selected, drag from its body to move it or from the corner handles to resize it; the cursor changes as you approach each area. Images stretch freely; hold **Shift** while dragging a handle to preserve their aspect ratio. The **Properties** panel lets you enter X, Y, width, and height in PDF points.
7. **Delete** (`Delete`): removes the selected object.
8. **Undo / Redo** (`Ctrl+Z` / `Ctrl+Y`): traverses the full session history, including redactions, strokes, and page operations.

The status bar shows **Unsaved changes** when there are active edits, and the window title is marked with `*`. When closing the document, opening another PDF, or quitting, the application offers **Save**, **Discard**, or **Cancel**.

### Export the result

1. Click **Export as…** (`Ctrl+Shift+S`) or use File → Export as…
2. Choose a name and folder different from the original PDF. The application refuses to save over the original and suggests `name-edited.pdf`, `name-edited-2.pdf`, … so as not to overwrite a previous export.
3. If there are redactions, confirm that they will be applied permanently.
4. Bene PDF applies the redactions, inserts the new text, images, and strokes, adds the page rotation, and finally reorders and deletes pages according to the working copy.
5. Bene PDF writes to a temporary file first, reopens it to validate it, and only then replaces the destination. If anything fails, the original file and the previous destination remain intact; the error message states this explicitly.

The exported file can be opened again and contains the applied text, images, strokes, redactions, image replacements, and page layout. Redaction removes the underlying text (not just covers it); on scanned pages it erases only the pixels in the marked region, and it deletes annotations and form fields whose area intersects the redaction. Document metadata and embedded attachments are outside the redaction region and are not sanitized.

To save only some pages, use **Page → Extract pages…**; extraction creates a new file and does not change the working session.

Encrypted PDFs cannot be exported in this iteration: PyMuPDF would need the owner password to preserve protection, and the application neither requests nor stores it. The **Export as…** action is disabled for those documents.

### Zoom and fit

- **Zoom in** / **Zoom out**: toolbar buttons, `Ctrl++` / `Ctrl+-`, or `Ctrl`+mouse wheel over the page.
- **100%**: `Ctrl+0`.
- **Fit width**: `Ctrl+1`.
- **Fit page**: `Ctrl+2`.
- Manual zoom ranges from 10% to 800%.
- When the window is resized, the fit modes recalculate the scale automatically.
- On HiDPI screens, rendering uses the real density to keep it sharp; at very high zoom levels, density is limited automatically to avoid running out of memory.

### Rotate the view

Click **Rotate view 90°** or press `Ctrl+R` to rotate the page on screen 90° clockwise. You can repeat it to reach 180° and 270°. The rotation is display-only: **it does not modify the PDF** and resets when another document is opened.

### Close and quit

- **Close document** (`Ctrl+W`) closes the current PDF and leaves the application open.
- **Quit** (`Ctrl+Q`, or File → Quit) closes the application.
- Opening another PDF automatically closes the previous document.

### Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Open PDF | `Ctrl+O` |
| Previous page | `PgUp` |
| Next page | `PgDn` |
| Zoom in | `Ctrl++` |
| Zoom out | `Ctrl+-` |
| Zoom 100% | `Ctrl+0` |
| Fit width | `Ctrl+1` |
| Fit page | `Ctrl+2` |
| Rotate view 90° | `Ctrl+R` |
| Select tool | `Ctrl+Shift+V` |
| Select region | `Ctrl+Shift+R` |
| Redact region | `Ctrl+Shift+X` |
| Add text | `Ctrl+T` |
| Insert image | `Ctrl+I` |
| Draw | `Ctrl+Shift+D` |
| Search | `Ctrl+F` |
| Find next | `F3` |
| Find previous | `Shift+F3` |
| Document information | `Ctrl+Alt+I` |
| Rotate page 90° | `Ctrl+Alt+R` |
| Move page up | `Ctrl+Alt+↑` |
| Move page down | `Ctrl+Alt+↓` |
| Delete page | `Ctrl+Alt+Delete` |
| Extract pages | `Ctrl+Alt+E` |
| Export as… | `Ctrl+Shift+S` |
| Undo | `Ctrl+Z` |
| Redo | `Ctrl+Y` |
| Delete object | `Delete` |
| Close document | `Ctrl+W` |
| Quit | `Ctrl+Q` |

### Errors and logging

If the file does not exist, is damaged, is not a PDF, or cannot be read, the application shows a dialog with the reason. Technical details are written to the log:

- Windows: `%LOCALAPPDATA%\bene-pdf\logs\bene.log`
- Linux: `$XDG_STATE_HOME/bene-pdf/logs/bene.log` or `~/.local/state/bene-pdf/logs/bene.log`

The log rotates at 2 MB, keeps three copies, and never contains the document text.

### Accessibility and keyboard

- All main controls have accessible names and descriptions: window, canvas, navigation, page selector, thumbnails, text dialog, drawing toolbar, and properties panel.
- Form labels are associated with their fields, and the `Tab` order follows a logical sequence: navigation → thumbnails → canvas, and text → font → size → color → alignment in the dialog.
- Each thumbnail announces “Page N”, and its tooltip indicates which page it leads to.
- The canvas has explicit focus and updates its description with the page, type, and dimensions.

Automated checks cover names, labels, and tab order. Before a distributable version, it should be reviewed with a real screen reader (Narrator on Windows or Orca on Linux).

### Large documents

The test suite includes tests with synthetic PDFs of **100 text pages** and **100 scanned pages**. They check opening, the classification of the first and last page, and rendering of both ends. They are marked as `slow` and are not run in the fast suite:

```powershell
pytest -m slow
```

### Build an executable

The executable is built with PyInstaller and the `build` extra:

```powershell
python -m pip install -e ".[dev,build]"
python scripts/build_app.py
```

The result is placed in `dist\BenePDF\BenePDF.exe`. The command includes the Liberation fonts, the MuPDF binaries, and the Qt plugins. To review the command without building it:

```powershell
python scripts/build_app.py --dry-run
```

You can also generate a single file with `--onefile`, although it takes longer to start. The executable does not need Python installed on the target machine.

### Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

- **Windows and Ubuntu:** `ruff check`, `ruff format --check`, `mypy`, and `pytest` with `QT_QPA_PLATFORM=offscreen`.
- **Windows:** coverage, slow tests (`pytest -m slow`), and the executable build.
- The `BenePDF-windows` artifact is published at the end of the packaging job.

### Limitations of this iteration

- Editing changes live in memory until they are exported; the original PDF is never modified.
- Encrypted PDFs cannot be exported while they remain protected.
- There is no OCR or printing; search only finds recognizable text, not scans.
- Thumbnails reflect page order and extra rotation, but are generated from the original PDF: added text, images, and redactions do not appear in them.
- View rotation is not saved to the file; page rotation is applied on export.
- Image replacement is not available for inline images, images inside forms, or images without a reliable `xref`.
- Drawing only supports freehand strokes: there are no straight lines, arrows, shapes, or highlighter yet, and pen pressure or tilt is not captured.
- A stroke is new vector content; it covers text but does not remove it. Use redaction for permanent removal.
- The thickness of a stroke is fixed when it is created; resizing changes its shape, not its line width.
- Redaction may affect objects that overlap the marked region; review it before exporting.
- Redaction removes page content, annotations, and form fields that intersect the region, but it does not clean document metadata or embedded attachments.
- If a particular page cannot be rendered, a warning is shown and the details are written to the log.
- The interface has been verified in offscreen mode on Windows (and in CI on Ubuntu); a visual review with a real display, DPI, and screen reader is still pending before a distributable version.
- Linux is tested in CI in offscreen mode but has not been validated visually.
- The executable includes Qt and MuPDF, so it takes up hundreds of MB. That is the cost of not requiring Python on the target machine.
- Executable checks in CI are limited to `--version` and the presence of resources; opening, editing, and exporting on a clean Windows machine is still a pending manual test.

## Commands

```powershell
bene                    # opens the application
bene document.pdf       # opens a PDF at startup
pytest                  # fast tests
pytest -m slow          # large documents and performance
pytest -m ui            # UI only
ruff check .            # lint
ruff format .           # formatting
mypy                    # static typing
python scripts/verify_env.py      # checks Python, PyMuPDF, and Qt
python scripts/benchmark_open.py  # measures the RNF-001 performance criterion
python scripts/build_app.py       # builds dist/BenePDF
python scripts/build_app.py --dry-run  # shows the PyInstaller command
```

To run the interface in a headless environment (CI):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
pytest -m ui
```

## Structure

```text
src/bene/
├── main.py           # entry point
├── bootstrap.py      # dependency composition
├── domain/           # models, rules, and errors
├── application/      # ports and use cases
├── infrastructure/   # adapters (PyMuPDF, storage, logs)
└── presentation/     # Qt window, viewer, and workers
```

The interface does not import PyMuPDF: it only knows the ports of the application layer. A test verifies that boundary.

## Licenses

The project is for personal use and is not distributed. It uses PyMuPDF under its AGPL-3.0 license, which prevents distributing the application without complying with that license. See [ADR-001](docs/decisions/ADR-001-motor-pdf.md).
