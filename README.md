<img width="786" height="1024" alt="stagcraft_logo" src="https://github.com/user-attachments/assets/5b871019-8657-46bb-9401-b9df965ed9e8" />

# sTagCraft

A local caption editor for LoRA training datasets.

Point it at a folder of images, open the browser, and edit Danbooru-style tag
captions with the whole dataset in view. Its main job is catching the
inconsistencies you cannot see one file at a time — the same gesture tagged
`head rest` in one frame and `chin rest` in another, a typo that quietly forks a
tag into two, a tag accidentally written twice in the same caption.

No dependencies, no build step, no config file. One `python3` command.

---

## Features

**Editing**

- Three-pane layout: file gallery, image with caption editor, dataset tag panel
- Autosave 0.7 s after you stop typing; `Ctrl+S` to force
- Captions are written straight to `.txt` files on disk — no database, no export step
- Tag chips under the editor; click one to remove it from the current frame

**Consistency checks**

- Full tag list with per-frame frequencies; rare tags (≤ 2 frames) highlighted
- Duplicate tags inside a single caption marked in red
- Near-duplicate tags across the dataset flagged in violet, with the candidates
  listed on hover — catches `looking down` / `looking downwards`,
  `eyes closed` / `closed eyes`, `smile` / `smiling`, and mid-word typos
- Frames with no caption marked red in the gallery

**Bulk operations**

- Rename a tag across every file at once; empty replacement deletes it
- Autocomplete on both rename fields, restricted to tags that actually exist,
  with a live preview of what the operation will do and how many frames it touches
- Checkbox selection in the gallery, then add or remove a tag on the selection
- Click any tag to filter the gallery down to the frames that use it

---

## Requirements

Python 3 and a browser. Nothing else — the whole thing runs on the standard
library. Tested on **Python 3.13**.

## Running

```bash
python3 main.py /path/to/dataset
python3 main.py /path/to/dataset --port 8777
```

The server binds to `127.0.0.1` only and opens your default browser. Press
`Ctrl+C` to stop.

The dataset folder is expected to look like this — images with same-named `.txt`
files beside them:

```
dataset/
├── 0001.png
├── 0001.txt      1girl, solo, looking down, indoors
├── 0002.png
├── 0002.txt
└── ...
```

Supported image extensions: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`. A missing
`.txt` is treated as an empty caption and created on first save.

### Optional: uv

If you have [uv](https://docs.astral.sh/uv/), it works too and is more
convenient for development:

```bash
uv run main.py /path/to/dataset     # same thing
uv run pytest                       # run the test suite
uv run pytest -v                    # ...with one line per case
uv run ruff check .                 # lint
```

`uv` is not required to *use* sTagCraft — only to run the tests and linters, which
are the one place where dev dependencies exist.

---

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `↑` / `↓` | previous / next frame |
| `j` / `k` | next / previous frame |
| `Ctrl+S` | save immediately |
| `Enter` (rename fields) | apply the rename |
| `↑` / `↓` / `Enter` (autocomplete) | pick a suggestion |
| `Esc` | close the suggestion list |

---

## How near-duplicate detection works

Four rules, applied in order of cost. Two tags are flagged when any of them fires:

1. **Same words, different order** — `eyes closed` / `closed eyes`
2. **One tag continues the other inside its last word** — `looking down` /
   `looking downwards`, `1girl` / `1girls`. A whole extra word does *not* count,
   so `blue eyes` / `blue eyes closed` stays quiet — those are usually two
   legitimate tags.
3. **Shared prefix inside a word** — `smile` / `smiling`, `cowboy shot` /
   `cowboy shoot`. The prefix must not end on a word boundary, otherwise
   `long hair` / `long sleeves` would collide.
4. **Levenshtein distance** ≤ 1 for short tags, ≤ 2 from 8 characters up —
   catches typos anywhere in the string, including the middle.

This is purely lexical. Two tags that mean the same thing but share no letters —
`head rest` / `chin rest` — will not be flagged, and no string metric would catch
them. The flag is a hint to look, not a verdict.

---

## Project layout

```
stagcraft/
├── main.py              entry point, argument parsing
├── server.py            HTTP handler and routes
├── dataset.py           the Dataset class: images, captions, tag counts
├── utilities.py         Levenshtein, near-duplicate rules, caption parsing
├── static/
│   ├── index.html
│   ├── app.css
│   └── app.js
└── tests/
```

Dependencies point one way only: `server` → `dataset` → `utilities`. Nothing in
`utilities` knows about files or HTTP, which is why it is the part with real test
coverage.

---

## Notes

- Files are written in place, immediately, with no undo. Keep the dataset under
  version control or take a copy before a bulk rename.
- The server has no authentication and is meant for `localhost` only. Do not
  expose the port.
- Opening `static/index.html` directly from the file manager will not work —
  the page fetches its data over HTTP and has to be served.
