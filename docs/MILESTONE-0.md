# Milestone 0 — Protocol and Packaging Proof

## Implemented

- PDF text-layer inspection and scan fallback, with a bundled PyMuPDF path for clean Macs.
- Conservative Xteink EPUB 2 packaging with NCX navigation and simple XHTML/CSS.
- Scan JPEG limits of 1000px and under 2MB, enforced by the validator.
- Stable `DocumentStructure` manifest embedded in the EPUB and written as a sidecar.
- Immutable, content-addressed original storage.
- Atomic derivative writes and approximate HTML preview.
- Deterministic package, manifest, spine, navigation, XML, resource, and Xteink profile checks.
- Token-authenticated loopback API.
- Separate stock and CrossPoint adapters.
- Exact transfer evidence levels, including CrossPoint readback hashing.
- Mock protocol regression tests for upload, listing, replacement, readback, and deletion.
- Native SwiftUI Mac shell that launches and supervises the bundled Python engine.
- One-file engine packaging and ad-hoc-signed `.app` assembly for local proof.
- Frozen-engine conversion and validation with Poppler/Homebrew removed from `PATH`.

## Hardware acceptance still required

- Open a generated EPUB on a physical stock X4 and record layout defects.
- Repeat on a physical X4 running CrossPoint.
- Confirm stock firmware endpoint behavior and destination path conventions against the purchased firmware version.
- Confirm CrossPoint endpoint behavior against the purchased firmware version.
- Run upload, list, replace, delete, and readback while the reader is in transfer mode.
- Replace ad-hoc signing with Developer ID signing and notarization before any external build.
- Replace ad-hoc packaging with a polished DMG installer for invited testers.
