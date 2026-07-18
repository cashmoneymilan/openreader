# OpenReader

OpenReader is a private, local-first macOS application that converts PDFs into conservative EPUB 2 books for Xteink readers. It preserves the original PDF, validates every generated EPUB, shows a conversion receipt, and supports stock Xteink and CrossPoint transfer sessions.

This repository currently contains the verified Milestone 0 vertical slice: a native SwiftUI application supervising a packaged Python conversion engine.

## Use the Mac app

The current private build supports macOS 14 or newer on Apple Silicon.

1. Build the application:

   ```bash
   ./scripts/package_macos.sh
   ```

2. Open it:

   ```bash
   open build/OpenReader.app
   ```

3. In OpenReader:

   - Drop a PDF onto the source card or choose **Choose PDF**.
   - Select **Create EPUB**.
   - Review the support tier, conversion mode, text retention, and validation result.
   - Use **Open Preview** to inspect the approximate result or **Show in Finder** to locate the EPUB.
   - To transfer wirelessly, start file-transfer mode on the reader, select its firmware, check the connection, and select **Send EPUB**.

The packaged app includes its Python runtime and PyMuPDF fallback. A destination Mac does not need Homebrew, Poppler, or a separate Python installation.

Application data is stored locally under:

```text
~/Library/Application Support/OpenReader/M0/
```

Closing the last OpenReader window also stops its private loopback engine.

## Development setup

Requirements:

- macOS 14 or newer
- Xcode/Swift command-line tools
- Python 3.12–3.14
- [`uv`](https://docs.astral.sh/uv/)

Install the locked Python environment:

```bash
uv sync --extra dev
```

Run the tests:

```bash
uv run pytest
```

Build only the SwiftUI client:

```bash
swift build -c release --package-path apps/macos
```

## Command-line conversion

Convert a PDF:

```bash
uv run openreader convert "/path/to/book.pdf" --output-dir ./build/library
```

Validate a generated EPUB:

```bash
uv run openreader validate "./build/library/derivatives/book.epub"
```

The conversion directory contains:

```text
originals/      content-addressed source PDFs
derivatives/    generated EPUB files
previews/       approximate HTML previews
manifests/      stable OpenReader structure manifests
```

Reflow conversion removes repeated running headers, footers, and standalone page numbers; detects chapter headings for navigation; preserves bold and italic spans; and embeds a rendered reference page when figures or complex layouts would otherwise be lost. Image-only scans still use page-image preservation.

## Curated books-folder workflow

OpenReader works best as a reading pipeline rather than as a device-sized archive:

```text
Incoming -> classify -> convert -> validate -> Library -> Queue -> reader -> Finished
```

Keep narrative books and long-form essays in EPUB for comfortable reflow. Keep research papers, manuals, equations, tables, and image-only scans PDF-first. A native, legally acquired DRM-free EPUB remains preferable to a converted PDF.

Audit a structured library and write a machine-readable report:

```bash
uv run python scripts/audit_books_library.py \
  "$HOME/Downloads/personal/books" \
  --output "$HOME/Downloads/personal/books/library-audit.json" \
  --strict
```

The audit validates every canonical EPUB against the conservative Xteink profile, detects duplicate PDFs, checks PDF/EPUB pairs, and confirms that queue files are hard-linked to their canonical EPUBs.

## Internal engine

For API development, run the authenticated loopback service directly:

```bash
uv run openreader serve --port 8765 --token local-development-token
```

Every `/v1/*` request requires:

```text
Authorization: Bearer local-development-token
```

The macOS app generates an ephemeral token automatically. Do not expose this control service to a LAN or the public internet.

## Build and verification commands

```bash
./scripts/build_engine.sh       # create the frozen Python engine
./scripts/package_macos.sh      # assemble and ad-hoc sign OpenReader.app
./scripts/verify_m0.sh          # test, convert, validate, package, and health-check
```

To use a different verification PDF:

```bash
./scripts/verify_m0.sh "/path/to/representative.pdf"
```

The verification script also converts with Poppler removed from `PATH`, proving the packaged engine is self-contained.

## Repository layout

```text
apps/macos/                 native SwiftUI application
engine/openreader_engine/   conversion, validation, API, and device adapters
tests/                      converter, API, and protocol fixtures
scripts/                    build, packaging, and acceptance automation
docs/                       protocol notes and Milestone 0 evidence
```

## Reader compatibility

OpenReader generates deliberately conservative, DRM-free EPUB 2 files. The files should open on readers that support standard EPUB, including Kobo, PocketBook, BOOX, and reMarkable. Kindle accepts EPUB through Send to Kindle, where Amazon converts it to a Kindle format.

There are two different compatibility levels:

| Reader | Generated EPUB | Direct send from OpenReader |
| --- | --- | --- |
| Xteink X4, stock firmware | Yes | Implemented; physical verification pending |
| Xteink X4, CrossPoint | Yes | Implemented; physical verification pending |
| Kobo | Expected | Not yet; export and sideload manually |
| PocketBook | Expected | Not yet; export and sideload manually |
| BOOX | Expected | Not yet; export or use BOOXDrop manually |
| reMarkable | Expected | Not yet; import through its app, web interface, or USB |
| Kindle | Via Send to Kindle conversion | Not yet |

Official format references: [Kobo](https://help.kobo.com/hc/en-us/articles/360017763713-File-formats-your-Kobo-eReader-and-Kobo-Books-app-support), [PocketBook](https://products.pocketbook.ch/), [BOOX](https://help.boox.com/hc/en-us/articles/25400769451540-Adjust-EPUB-and-Similar), [reMarkable](https://support.remarkable.com/articles/Knowledge/importing-and-exporting-files), and [Kindle](https://www.amazon.com/sendtokindle).

Additional limitations:

- Stock Xteink and CrossPoint use separate adapters and evidence levels.
- CrossPoint readback can establish cryptographic verification; a stock upload acknowledgement cannot.
- X3 compatibility is not claimed without physical testing.
- The current app is ad-hoc signed. Developer ID signing and notarization are required for a production macOS release.

See [Milestone 0](docs/MILESTONE-0.md), [protocol notes](docs/PROTOCOLS.md), and the [acceptance report](docs/M0-ACCEPTANCE-REPORT.md) for implementation evidence.

## Repository policy

The source repository is public for development and review. Milestone 0 remains experimental: do not present the app as a production release or claim physical-reader acceptance until those tests have passed.
