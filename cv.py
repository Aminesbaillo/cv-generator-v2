"""Single-file CV generator.

Usage:
    python cv.py <path-to-cv.json>
    python cv.py <path-to-cv.json> --pdf
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from html import escape
from pathlib import Path

EMBEDDED_IMAGE_PREFIXES = ("data:image/", "http://", "https://")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name} - CV</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main class="page">
    <aside class="sidebar">
      {photo_block}
      <section class="sidebar-block contact">
        <h2>Contact</h2>
        {contact_block}
      </section>
      {education_block}
      {skills_block}
      {languages_block}
      {strengths_block}
    </aside>
    <section class="content">
      <header class="hero">
        <h1>{name}</h1>
        <p class="headline">{headline}</p>
      </header>
      {summary_block}
      {experience_block}
      {projects_block}
    </section>
  </main>
</body>
</html>
"""

TEX_TEMPLATE = r"""\documentclass[10pt,a4paper,withhyper]{{altacv}}
\usepackage{{paracol}}
\iftutex
  \setmainfont{{Lato}}
\else
  \usepackage[default]{{lato}}
\fi
\definecolor{{Graphite}}{{HTML}}{{1C1C1C}}
\definecolor{{Emerald}}{{HTML}}{{1B5E20}}
\definecolor{{SilverGrey}}{{HTML}}{{808080}}
\colorlet{{heading}}{{Graphite}}
\colorlet{{headingrule}}{{Emerald}}
\colorlet{{accent}}{{Emerald}}
\colorlet{{emphasis}}{{Graphite}}
\colorlet{{body}}{{SilverGrey}}
\colorlet{{tagline}}{{Emerald}}
\newcommand{{\cvproject}}[2]{{%
  \textcolor{{accent}}{{\textbf{{#1}}}}%
  \hfill {{\small\textcolor{{accent!80!black}}{{\textit{{#2}}}}}}\\\[-0.2ex]
}}
\renewcommand{{\cvItemMarker}}{{{{\small\textbullet}}}}
\renewcommand{{\cvRatingMarker}}{{\faCircle}}
\begin{{document}}
\newgeometry{{left=1.2cm,right=1cm,top=.5cm,bottom=0.4cm}}
\name{{\LARGE {name}}}
\tagline{{{headline}}}
{photo_block}
{personal_info_block}
\makecvheader
{summary_block}
\AtBeginEnvironment{{itemize}}{{\small}}
\columnratio{{0.4}}
\begin{{paracol}}{{2}}
{education_block}
{skills_block}
{languages_block}
{strengths_block}
\switchcolumn
{experience_block}
{projects_block}
\end{{paracol}}
\end{{document}}
"""

CSS_CONTENT = """* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", Arial, sans-serif;
  background: #e9ecef;
  color: #1c1c1c;
}
.page {
  width: 210mm;
  min-height: 297mm;
  margin: 6px auto;
  background: #ffffff;
  display: grid;
  grid-template-columns: 34% 66%;
  box-shadow: 0 18px 40px rgba(0,0,0,0.08);
  overflow: hidden;
}
.sidebar {
  background: #f4f8f4;
  padding: 16px 15px;
  border-right: 4px solid #1b5e20;
}
.content { padding: 18px 20px 16px; }
.photo {
  width: 104px; height: 104px;
  object-fit: cover; border-radius: 50%;
  display: block; margin: 0 auto 12px;
  border: 3px solid #1b5e20;
}
.hero {
  border-bottom: 3px solid #1b5e20;
  padding-bottom: 8px; margin-bottom: 12px;
}
h1 { margin: 0; font-size: 27px; letter-spacing: 0.4px; }
.headline { margin: 4px 0 0; color: #1b5e20; font-size: 14px; font-weight: 700; }
h2 { margin: 0 0 7px; font-size: 15px; color: #1b5e20; text-transform: uppercase; letter-spacing: 0.8px; }
h3 { margin: 0; font-size: 12.5px; }
.sidebar-block, .content-block { margin-bottom: 11px; }
.entry { margin-bottom: 9px; break-inside: avoid; }
.entry-head { display: flex; gap: 12px; justify-content: space-between; align-items: baseline; }
.entry-head span { color: #1b5e20; font-size: 11px; font-weight: 700; white-space: nowrap; }
.muted { color: #666; margin: 2px 0 5px; font-size: 11px; }
p, li { font-size: 11.7px; line-height: 1.3; }
ul { margin: 5px 0 0 15px; padding: 0; }
.project p { margin: 3px 0 0; }
.sidebar .sidebar-block .sidebar-block { margin-bottom: 7px; }
.contact p { margin: 2px 0; }
.project .entry-head { align-items: center; }
.project .entry-head h3 { font-size: 13px; color: #1c1c1c; }
.project .entry-head span { font-size: 10.5px; font-weight: 600; color: #4a4a4a; }
.project p { color: #333; }
@media print {
  @page { size: A4; margin: 0; }
  body { background: #fff; }
  .page { margin: 0; box-shadow: none; }
}
"""

BULLET_MAX_CHARS = 220
SUMMARY_MAX_ITEMS = 5


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_string_list(value: object) -> bool:
    return isinstance(value, list) and all(_is_non_empty_string(item) for item in value)


def validate_cv(config: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    basics = config.get("basics")
    if not isinstance(basics, dict):
        return ["ERROR: basics must be an object."], warnings

    for field in ["name", "email", "headline"]:
        if not _is_non_empty_string(basics.get(field)):
            errors.append(f"ERROR: basics.{field} must be a non-empty string.")
    if not _validate_string_list(basics.get("summary")):
        errors.append("ERROR: basics.summary must be a list of non-empty strings.")

    sections = config.get("sections", {})
    if sections and not isinstance(sections, dict):
        errors.append("ERROR: sections must be an object when provided.")

    if not isinstance(config.get("education", []), list):
        errors.append("ERROR: education must be a list.")
    if not isinstance(config.get("skills", []), list):
        errors.append("ERROR: skills must be a list.")
    if not isinstance(config.get("experience", []), list):
        errors.append("ERROR: experience must be a list.")
    if not isinstance(config.get("projects", []), list):
        errors.append("ERROR: projects must be a list.")
    if not _validate_string_list(config.get("languages", [])):
        errors.append("ERROR: languages must be a list of non-empty strings.")
    if not _validate_string_list(config.get("strengths", [])):
        errors.append("ERROR: strengths must be a list of non-empty strings.")

    core = {
        "education": config.get("education", []),
        "skills": config.get("skills", []),
        "experience": config.get("experience", []),
        "projects": config.get("projects", []),
        "summary": basics.get("summary", []),
    }
    for key, values in core.items():
        if sections.get(key, True) and not values:
            errors.append(f"ERROR: section '{key}' is enabled but empty.")

    summary = basics.get("summary", [])
    if isinstance(summary, list) and len(summary) > SUMMARY_MAX_ITEMS:
        warnings.append(
            f"WARN: summary has {len(summary)} items (>{SUMMARY_MAX_ITEMS}); may overflow one page."
        )

    for entry in config.get("experience", []):
        if not isinstance(entry, dict):
            continue
        for bullet in entry.get("bullets", []):
            if isinstance(bullet, str) and len(bullet) > BULLET_MAX_CHARS:
                warnings.append(
                    f"WARN: long bullet in '{entry.get('title', '?')}' ({len(bullet)} chars)."
                )

    return errors, warnings


def tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in value)


def _tex_item_list(items: list[str]) -> str:
    return "\n".join(f"\\item {tex_escape(item)}" for item in items)


def _html_education(entries: list[dict]) -> str:
    rows = "".join(
        f"""
        <article class="entry">
          <div class="entry-head">
            <h3>{escape(e["degree"])}</h3>
            <span>{escape(e["dates"])}</span>
          </div>
          <p class="muted">{escape(e["institution"])} | {escape(e["location"])}</p>
        </article>"""
        for e in entries
    )
    return f'<section class="sidebar-block"><h2>Education</h2>{rows}</section>'


def _html_skills(groups: list[dict]) -> str:
    rows = "".join(
        f"""
        <section class="sidebar-block">
          <h3>{escape(g["category"])}</h3>
          <p>{escape(", ".join(g["items"]))}</p>
        </section>"""
        for g in groups
    )
    return f'<section class="sidebar-block"><h2>Skills</h2>{rows}</section>'


def _html_languages(items: list[str]) -> str:
    lis = "".join(f"<li>{escape(i)}</li>" for i in items)
    return f'<section class="sidebar-block"><h2>Languages</h2><ul>{lis}</ul></section>'


def _html_strengths(items: list[str]) -> str:
    lis = "".join(f"<li>{escape(i)}</li>" for i in items)
    return f'<section class="sidebar-block"><h2>Strengths</h2><ul>{lis}</ul></section>'


def _html_summary(items: list[str]) -> str:
    lis = "".join(f"<li>{escape(i)}</li>" for i in items)
    return f'<section class="content-block"><h2>Professional Summary</h2><ul>{lis}</ul></section>'


def _html_experience(entries: list[dict]) -> str:
    rows = "".join(
        f"""
        <article class="entry">
          <div class="entry-head">
            <h3>{escape(e["title"])} | {escape(e["company"])}</h3>
            <span>{escape(e["dates"])}</span>
          </div>
          <p class="muted">{escape(e["location"])}</p>
          <ul>{''.join(f"<li>{escape(b)}</li>" for b in e["bullets"])}</ul>
        </article>"""
        for e in entries
    )
    return f'<section class="content-block"><h2>Professional Experience</h2>{rows}</section>'


def _html_projects(entries: list[dict]) -> str:
    rows = "".join(
        f"""
        <article class="entry project">
          <div class="entry-head">
            <h3>{escape(p["name"])}</h3>
            <span>{escape(p["stack"])}</span>
          </div>
          <p>{escape(p["description"])}</p>
        </article>"""
        for p in entries
    )
    return f'<section class="content-block"><h2>Selected Projects</h2>{rows}</section>'


def render_html(data: dict) -> str:
    basics = data["basics"]
    sections = data.get("sections", {})
    photo_value = basics.get("photo")
    photo_block = ""
    if photo_value:
        photo_src = photo_value if _is_embedded_or_remote_image(photo_value) else Path(photo_value).name
        photo_block = f'<img class="photo" src="{escape(photo_src)}" alt="{escape(basics["name"])}">'

    contact_parts = [basics.get("email", ""), basics.get("phone", ""), basics.get("location", ""), basics.get("linkedin", "")]
    github = basics.get("github", "")
    if github:
        contact_parts.append(github)
    contact_block = "".join(f"<p>{escape(p)}</p>" for p in contact_parts if p)

    return HTML_TEMPLATE.format(
        name=escape(basics["name"]),
        headline=escape(basics["headline"]),
        photo_block=photo_block,
        contact_block=contact_block,
        education_block=_html_education(data["education"]) if sections.get("education", True) else "",
        skills_block=_html_skills(data["skills"]) if sections.get("skills", True) else "",
        languages_block=_html_languages(data["languages"]) if sections.get("languages", True) else "",
        strengths_block=_html_strengths(data["strengths"]) if sections.get("strengths", True) else "",
        summary_block=_html_summary(basics.get("summary", [])) if sections.get("summary", True) else "",
        experience_block=_html_experience(data["experience"]) if sections.get("experience", True) else "",
        projects_block=_html_projects(data["projects"]) if sections.get("projects", True) else "",
    )


def _tex_education(entries: list[dict]) -> str:
    body = "\n\n\\divider\n\n".join(
        "\\cvevent{{{degree}}}{{{inst}}}{{{dates}}}{{{loc}}}".format(
            degree=tex_escape(e["degree"]),
            inst=tex_escape(e["institution"]),
            dates=tex_escape(e["dates"]),
            loc=tex_escape(e["location"]),
        )
        for e in entries
    )
    return f"\\cvsection{{Education}}\n{body}"


def _tex_skills(groups: list[dict]) -> str:
    body = "\n\n\\divider\\smallskip\n\n".join(
        "\\textbf{{{cat}}}\\\\\n{items}".format(
            cat=tex_escape(g["category"]),
            items=tex_escape(", ".join(g["items"])),
        )
        for g in groups
    )
    return f"\\cvsection{{Skills}}\n{body}"


def _tex_languages(items: list[str]) -> str:
    body = " \\\\\n".join(tex_escape(i) for i in items)
    return f"\\cvsection{{Languages}}\n{body}"


def _tex_strengths(items: list[str]) -> str:
    body = "\n".join(
        "\\item \\textbf{{{key}}} --- {rest}".format(
            key=tex_escape(i.split(" -- ")[0]),
            rest=tex_escape(" -- ".join(i.split(" -- ")[1:])),
        )
        for i in items
    )
    return f"\\cvsection{{Strengths}}\n\\begin{{itemize}}\n{body}\n\\end{{itemize}}"


def _tex_summary(items: list[str]) -> str:
    body = _tex_item_list(items)
    return (
        "\\begin{adjustwidth}{0cm}{0.2cm}\n"
        "\\cvsection{Professional Summary}\n"
        "\\setlist[itemize]{itemsep=0pt, topsep=2pt}\n"
        f"\\begin{{itemize}}\n{body}\n\\end{{itemize}}\n"
        "\\end{adjustwidth}"
    )


def _tex_experience(entries: list[dict]) -> str:
    body = "\n\n\\divider\n\n".join(
        "\\cvevent{{{title}}}{{{company}}}{{{dates}}}{{{loc}}}\n"
        "\\begin{{itemize}}\n{bullets}\n\\end{{itemize}}".format(
            title=tex_escape(e["title"]),
            company=tex_escape(e["company"]),
            dates=tex_escape(e["dates"]),
            loc=tex_escape(e["location"]),
            bullets=_tex_item_list(e["bullets"]),
        )
        for e in entries
    )
    return f"\\cvsection{{Professional Experience}}\n{body}"


def _tex_projects(entries: list[dict]) -> str:
    body = "\n\n\\divider\n\n".join(
        "\\cvproject{{{name}}}{{{stack}}}\n{{\\small {desc}}}".format(
            name=tex_escape(p["name"]),
            stack=tex_escape(p["stack"]),
            desc=tex_escape(p["description"]),
        )
        for p in entries
    )
    return f"\\cvsection{{Selected Projects}}\n{body}"


def render_tex(data: dict) -> str:
    basics = data["basics"]
    sections = data.get("sections", {})
    personal_lines = []
    if basics.get("email"):
        personal_lines.append(f"  \\email{{{tex_escape(basics['email'])}}}")
    if basics.get("phone"):
        personal_lines.append(f"  \\phone{{{tex_escape(basics['phone'])}}}")
    if basics.get("location"):
        personal_lines.append(f"  \\location{{{tex_escape(basics['location'])}}}")

    linkedin = basics.get("linkedin", "")
    if linkedin:
        personal_lines.append(f"  \\linkedin{{{tex_escape(linkedin.rstrip('/').split('/')[-1])}}}")
    github = basics.get("github", "")
    if github:
        personal_lines.append(f"  \\github{{{tex_escape(github.rstrip('/').split('/')[-1])}}}")

    personal_block = "\\personalinfo{%\n" + "\n".join(personal_lines) + "\n}" if personal_lines else ""
    photo_value = basics.get("photo", "")
    photo_block = "\\photoR{2.5cm}{photo}" if photo_value and not _is_embedded_or_remote_image(photo_value) else ""

    return TEX_TEMPLATE.format(
        name=tex_escape(basics["name"]),
        headline=tex_escape(basics["headline"]),
        personal_info_block=personal_block,
        photo_block=photo_block,
        summary_block=_tex_summary(basics.get("summary", [])) if sections.get("summary", True) else "",
        education_block=_tex_education(data["education"]) if sections.get("education", True) else "",
        skills_block=_tex_skills(data["skills"]) if sections.get("skills", True) else "",
        languages_block=_tex_languages(data["languages"]) if sections.get("languages", True) else "",
        strengths_block=_tex_strengths(data["strengths"]) if sections.get("strengths", True) else "",
        experience_block=_tex_experience(data["experience"]) if sections.get("experience", True) else "",
        projects_block=_tex_projects(data["projects"]) if sections.get("projects", True) else "",
    )


def _find_browser() -> str | None:
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for name, fallbacks in [("msedge", edge_paths), ("chrome", chrome_paths)]:
        found = shutil.which(name)
        if found:
            return found
        for path in fallbacks:
            if Path(path).exists():
                return path
    return None


def _build_browser_env(runtime_root: Path) -> dict[str, str]:
    local_app = runtime_root / "LocalAppData"
    app_data = runtime_root / "AppData"
    temp_dir = runtime_root / "Temp"
    user_profile = runtime_root / "UserProfile"
    for path in [local_app, app_data, temp_dir, user_profile]:
        path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(local_app)
    env["APPDATA"] = str(app_data)
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["USERPROFILE"] = str(user_profile)
    return env


def _wait_for_pdf(pdf_path: Path, timeout_seconds: float = 5.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return True
        time.sleep(0.2)
    return pdf_path.exists() and pdf_path.stat().st_size > 0


def _is_embedded_or_remote_image(value: str) -> bool:
    return value.lower().startswith(EMBEDDED_IMAGE_PREFIXES)


def export_pdf(html_path: Path, pdf_path: Path) -> bool:
    browser = _find_browser()
    if not browser:
        print("WARN: No Edge or Chrome found; skipping PDF export.")
        return False

    runtime_root = pdf_path.parent / ".pdf-export-runtime"
    profile_dir = runtime_root / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--disable-crash-reporter",
        "--disable-breakpad",
        "--run-all-compositor-stages-before-draw",
        f"--user-data-dir={profile_dir}",
        f"--print-to-pdf={pdf_path}",
        html_path.as_uri(),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=_build_browser_env(runtime_root),
        )
        if _wait_for_pdf(pdf_path):
            return True
        output = "\n".join(part for part in [result.stderr.strip(), result.stdout.strip()] if part)
        print(f"WARN: PDF export failed (exit {result.returncode}).")
        if output:
            print(output[:500])
        return False
    except Exception as exc:
        print(f"WARN: PDF export error: {exc}")
        return False


def generate(config_path: Path, out_dir: Path, with_pdf: bool) -> int:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: config file not found: {config_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON ({exc.msg}) at line {exc.lineno}, column {exc.colno}.")
        return 1

    errors, warnings = validate_cv(payload)
    for issue in errors + warnings:
        print(issue)
    if errors:
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    output_basename = payload.get("output_basename", "cv")

    html_path = out_dir / f"{output_basename}.html"
    tex_path = out_dir / f"{output_basename}.tex"
    css_path = out_dir / "style.css"

    html_path.write_text(render_html(payload), encoding="utf-8")
    tex_path.write_text(render_tex(payload), encoding="utf-8")
    css_path.write_text(CSS_CONTENT, encoding="utf-8")

    generated = [html_path, tex_path, css_path]

    photo_value = payload.get("basics", {}).get("photo")
    if isinstance(photo_value, str) and photo_value.strip() and not _is_embedded_or_remote_image(photo_value):
        photo_path = Path(photo_value)
        if not photo_path.is_absolute():
            photo_path = config_path.parent / photo_path
        if photo_path.exists():
            photo_dest = out_dir / photo_path.name
            shutil.copy2(photo_path, photo_dest)
            generated.append(photo_dest)

    if with_pdf:
        pdf_path = out_dir / f"{output_basename}.pdf"
        if export_pdf(html_path, pdf_path):
            generated.append(pdf_path)

    print("Generated files:")
    for path in generated:
        print(f" {path.resolve()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CV outputs from a self-contained JSON file.")
    parser.add_argument("config", help="Path to CV JSON file.")
    parser.add_argument("--pdf", action="store_true", help="Also export PDF via Edge/Chrome headless.")
    parser.add_argument("--out-dir", default="build", help="Output directory. Default: build")
    args = parser.parse_args()
    return generate(Path(args.config).resolve(), Path(args.out_dir).resolve(), args.pdf)


if __name__ == "__main__":
    raise SystemExit(main())
