# OpenReader Milestone 0 Acceptance Report

Date: 2026-07-17

Specification: `/Users/milanmuriithi/Downloads/openreader-v1-spec-rewrite.md`

## Verdict

**Software acceptance: PASS.** The private Milestone 0 implementation proves PDF ingestion, reconstruction, Xteink-profile EPUB 2 packaging, validation, preview generation, adapter contracts, a token-authenticated loopback engine, a native SwiftUI shell, and self-contained app packaging.

**Physical-device acceptance: PENDING.** A stock X4 and a CrossPoint X4 were not available for on-device rendering and live transfer tests. No claim stronger than the recorded adapter evidence is made.

## Specification corrections applied

- Conversion quality is the product wedge; reconciliation is the trust layer.
- The release sequence is private M0–M2, followed by the public/open-source M3 release.
- M0 was added to prove protocol behavior and packaging before broader product work.
- Support tiers, quantitative quality gates, stable structure manifests, retention policy, exact transfer-evidence states, initiated sync sessions, and a concrete SwiftUI + packaged-Python architecture were specified.
- The minimal browser catalog, OPDS surface, automation rules, and the post-v1 reading-system north star were retained without turning v1 into a separate TypeScript product.

## Automated evidence

- `7 passed` Python unit/integration tests.
- API authentication, conversion, reporting, validation, and stock/CrossPoint adapter fixture tests passed.
- All 12 PDFs in `/Users/milanmuriithi/Downloads/personal/books` produced validator-clean EPUBs.
- 11 documents were classified Tier A / reflow with normalized text retention from 99.89% to 100%.
- `Forrester_Jay_W_World_Dynamics_2nd_ed_1973 (1).pdf` was honestly classified Tier B / page images and passed package validation.
- The XML-forbidden control character found in the Timothy Keller source was stripped before XHTML generation and retained as a regression fixture.
- The representative scripted proof generated a valid EPUB 2 derivative and approximate HTML preview from `Elements of Style.pdf`.
- The frozen engine converted and validated that fixture with `PATH=/usr/bin:/bin`, proving the bundle does not require Homebrew, Poppler, or a separate Python installation.
- The app bundle passed strict deep code-signature verification with its current private ad-hoc signature.
- A signature-preserving private archive was produced at `build/OpenReader-M0-private-macOS-arm64.zip` (SHA-256 `49a58af8fbaa0ed8b4b04efd0dd05bb3eb1723adfe3f72939fd46b32cd8c290c`) and its extracted app passed strict deep signature verification.

## Native app evidence

The packaged `OpenReader.app` was launched as a clean process and tested through the macOS UI with `Timothy-Keller-The-Freedom-of-Self-Forgetfulness.pdf` from the mapped books folder.

The UI reported:

- engine ready;
- immutable source held;
- Tier A / reflow;
- EPUB 2.0 package passed;
- 99.97% normalized text retention (displayed as 100.0%);
- 48 source pages and 6 XHTML sections;
- preview, reveal, device probe, and send controls available.

The final UI uses a native SwiftUI/macOS presentation: unified toolbar, system typography and materials, semantic status colors, standard controls, a quiet workflow sidebar, and an adaptive conversion receipt rather than a custom web-style dashboard.

Closing the last app window terminated both the Swift process and its embedded local engine.

## Protocol basis

- CrossPoint behavior follows the official [web-server guide](https://github.com/crosspoint-reader/crosspoint-reader/blob/develop/docs/webserver.md) and [endpoint reference](https://github.com/crosspoint-reader/crosspoint-reader/blob/develop/docs/webserver-endpoints.md).
- The stock X4 `/list` and `/edit` behavior is based on the public [CrossX stock-firmware service implementation](https://github.com/jtvargas/crosspoint-app/blob/main/SendToX4/Services/StockFirmwareService.swift), with deliberately weaker evidence because the stock protocol does not expose CrossPoint-style readback.

## Remaining gates

1. Open representative Tier A and Tier B books on a physical stock X4 and inspect typography, navigation, images, startup time, and memory behavior.
2. Repeat on a physical X4 running CrossPoint.
3. Exercise real stock upload and CrossPoint upload/list/replace/delete/readback while transfer mode is active.
4. Record firmware versions and promote only observed behavior into the compatibility matrix.
5. Obtain a Developer ID certificate, sign, notarize, staple, and verify a private tester DMG before distributing outside this Mac.
6. Treat X3 support as unverified until a physical X3 is tested; the current launch-device contract is X4.

## Re-run

```bash
cd "/Users/milanmuriithi/Documents/Codex/2026-07-15/if-i/openreader"
./scripts/verify_m0.sh
```
