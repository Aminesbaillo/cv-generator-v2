# Architecture

## Overview

The project has two user-facing entry points:

- `cv-form.html` is a standalone browser app for editing CV data visually.
- `cv.py` is a standalone Python CLI for generating output files from a JSON CV definition.

There is no backend server and no third-party runtime dependency.

## Data Flow

1. The user edits or uploads CV data in `cv-form.html`.
2. The form keeps the preview synchronized with the current form state.
3. `Export JSON` downloads a self-contained JSON file.
4. `cv.py` reads that JSON and writes HTML, TeX, CSS, and optional PDF output.

## Photo Handling

The form supports local photo upload by storing the image as a `data:image/...` URL in `basics.photo`.

`cv.py` supports:

- embedded `data:image/...` values in generated HTML,
- remote `http://` and `https://` image URLs in generated HTML,
- local image paths copied into `build/` for generated HTML and TeX.

TeX photo output is skipped for embedded or remote images because LaTeX expects a local file.
