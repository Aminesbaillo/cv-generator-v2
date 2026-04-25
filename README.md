# CV Generator V2

Local, dependency-free CV builder and generator.

## Files

- `cv-form.html` - browser-based CV form with live preview, profile presets, JSON upload/export, photo upload, and print-to-PDF.
- `cv.py` - command-line generator that converts a self-contained CV JSON file into HTML, TeX, and optionally PDF.
- `sample_cv.json` - anonymized working CV data example.
- `requirements.txt` - Python dependency list. It is intentionally empty because the runtime uses the standard library only.

## Setup

Create and activate the virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Use The Form

Open `cv-form.html` directly in a browser.

Main actions:

- Select a profile to prefill the form.
- Upload JSON to load a saved CV.
- Upload Photo to embed a local image into the preview and exported JSON.
- Export JSON to save a `cv.py` compatible file.
- Download PDF to print the live preview.

## Generate Outputs From JSON

```powershell
.\.venv\Scripts\python.exe cv.py sample_cv.json
```

Outputs are written to `build/`:

- `<output_basename>.html`
- `<output_basename>.tex`
- `style.css`

Optional PDF export through local Edge or Chrome:

```powershell
.\.venv\Scripts\python.exe cv.py sample_cv.json --pdf
```

## JSON Schema

The exported JSON is self-contained and matches the schema expected by `cv.py`:

```json
{
  "role_name": "Generated CV",
  "output_basename": "generated_cv",
  "show_github": true,
  "sections": {},
  "basics": {
    "name": "",
    "email": "",
    "phone": "",
    "location": "",
    "linkedin": "",
    "github": "",
    "headline": "",
    "photo": "",
    "summary": []
  },
  "languages": [],
  "strengths": [],
  "education": [],
  "skills": [],
  "experience": [],
  "projects": []
}
```
