# Screenshots

Product screenshots for the release notes. **One per release**, so the
[`RELEASE_NOTES.md`](../RELEASE_NOTES.md) version history always has a matching
visual.

| File | Version | Notes |
|---|---|---|
| `app-ui.svg` | current | Self-contained **vector** reproduction of the landing UI — always renders on GitHub, no capture step. Used at the top of the main README. |
| `app-ready.png` | current | Optional **raster** screengrab of the ready-state landing screen (run `capture.command`) |
| `app-v1.1.png` | v1.1 | Archived raster copy for the v1.1 notes |

## Regenerate (repeatable, one command)

`capture.command` screenshots the app's landing page straight from a locally
running instance — no manual cropping.

```bash
./screenshots/capture.command
```

It will:
1. Start the app if it isn't already running (`python3 server.py`).
2. Render `http://127.0.0.1:8765/` with headless Google Chrome at 2× scale.
3. Save `screenshots/app-ready.png` **and** an archived `screenshots/app-<version>.png`.

Requirements: Google Chrome installed (the app's own setup already gives you
everything else). If Chrome is sandbox‑restricted on a given machine, grant it
Files‑and‑Folders access in System Settings → Privacy, or capture manually with
`⌘⇧4` and save as `app-ready.png`.
