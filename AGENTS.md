# OpenReader

Public development repository. Do not publish a production release or claim untested hardware compatibility before the relevant acceptance gates pass.

## Architecture

- `engine/openreader_engine`: cross-platform Python conversion, validation, API, and device adapters.
- `apps/macos`: SwiftUI client that launches and supervises the bundled engine.
- `tests`: fixture-driven converter, validator, and protocol adapter tests.
- `scripts`: packaging and Milestone 0 verification.
- `docs`: protocol decisions and acceptance evidence.

## Product invariants

- Originals are immutable.
- Derivatives are written atomically and carry a stable structure manifest.
- Xteink device state is evidence-backed; never infer cryptographic verification from an upload response or filename listing.
- Device deletions are never automatic in v1.
- The internal control listener is loopback-only and token-authenticated.
- Stock and CrossPoint firmware are separate adapters with separate capabilities.

## Commands

```bash
uv sync --extra dev
uv run pytest
uv run openreader convert <pdf> --output-dir build/m0
./scripts/build_engine.sh
./scripts/package_macos.sh
```
