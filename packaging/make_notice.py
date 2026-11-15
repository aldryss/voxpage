"""Génère NOTICE.txt : composants Python embarqués (licences lues dans l'environnement de build) et voix.

Usage : python packaging/make_notice.py SORTIE.txt
À lancer dans l'environnement où PyInstaller construit l'exécutable.
"""

import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import fetch_ocr  # noqa: E402
from fetch_voices import VOICES  # noqa: E402

LICENSE_FILE = re.compile(r"(^|/)(licen[cs]e|copying|notice|copyright)[^/]*$", re.I)
MAX_TEXT = 40_000  # par composant

STATIC = """\
Composants non Python embarqués ou utilisés par les composants ci-dessous
-------------------------------------------------------------------------
- Python (PSF License) et son interpréteur, dans _internal/.
- PyInstaller (GPL-2.0 avec exception pour les programmes produits) : amorçage de l'exécutable.
- ONNX Runtime (MIT, Microsoft), fourni avec sherpa-onnx.
- eSpeak NG (GPL-3.0-or-later, https://github.com/espeak-ng/espeak-ng) : phonémisation des voix
  Piper. Le code est compilé dans sherpa-onnx ; les données de langue se trouvent dans
  voices/<voix>/espeak-ng-data. Code source : voir le dépôt ci-dessus et celui de sherpa-onnx.
- PDFium (BSD-3-Clause / Apache-2.0, Google), fourni avec pypdfium2 (pdfium.dll).
- wxWidgets (wxWindows Library Licence 3.1), fourni avec wxPython.
- LAME (LGPL), compilé dans lameenc (LGPL-3.0) pour l'encodage MP3.
- OpenCV (Apache-2.0), fourni avec opencv-python-headless (lecture et traitement d'images pour l'OCR).
- GEOS (LGPL-2.1), fourni avec Shapely ; Clipper (licence Boost), fourni avec pyclipper.
"""


def _requirements(dist: metadata.Distribution) -> list[str]:
    names = []
    for req in dist.requires or []:
        if "extra ==" in req:
            continue
        m = re.match(r"[A-Za-z0-9_.\-]+", req)
        if m:
            names.append(m.group(0))
    return names


def _roots() -> list[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    deps = project["dependencies"] + project["optional-dependencies"]["gui"]
    return [re.match(r"[A-Za-z0-9_.\-]+", d).group(0) for d in deps]


def _closure() -> list[metadata.Distribution]:
    seen: dict[str, metadata.Distribution] = {}
    todo = _roots()
    while todo:
        name = todo.pop()
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        key = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
        if key not in seen:
            seen[key] = dist
            todo += _requirements(dist)
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def _license_name(dist: metadata.Distribution) -> str:
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr
    lic = (md.get("License") or "").strip()
    if lic and len(lic) < 80 and "\n" not in lic:
        return lic
    classifiers = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if "License ::" in c]
    return ", ".join(classifiers) or "voir le texte ci-dessous"


def _license_texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    out = []
    for f in dist.files or []:
        if LICENSE_FILE.search(str(f).replace("\\", "/")):
            try:
                out.append((str(f), f.locate().read_bytes().decode("utf-8", errors="replace")))
            except OSError:
                pass
    return out


def build() -> str:
    parts = ["VOXPAGE - NOTICES DE LICENCES TIERCES", "=" * 38, ""]
    parts.append("Voxpage embarque les composants suivants. Chacun reste soumis à sa propre licence.\n")
    parts += ["VOIX", "----"]
    for v in VOICES:
        parts.append(f"* {v['id']} : {v['attribution']}\n  Licence : {v['license']} - {v['source']}")
    parts.append("\nVoir aussi voices/README.md (réserve sur la licence du checkpoint d'origine).\n")
    parts += ["MODÈLES DE RECONNAISSANCE DE CARACTÈRES (OCR)", "-------------------------------------------"]
    for m in fetch_ocr.MODELS:
        parts.append(f"* ocr/{m['file']} : {m['role']}\n  Licence : {fetch_ocr.LICENSE} - {fetch_ocr.SOURCE}")
    parts.append("")
    parts += [STATIC, "COMPOSANTS PYTHON", "-----------------"]
    dists = _closure()
    for d in dists:
        md = d.metadata
        home = md.get("Home-page") or ""
        parts.append(f"* {md['Name']} {md['Version']} - {_license_name(d)}  {home}".rstrip())
    parts.append("")
    for d in dists:
        for name, text in _license_texts(d):
            parts += ["=" * 78, f"{d.metadata['Name']} {d.metadata['Version']} - {name}", "=" * 78]
            parts.append(text[:MAX_TEXT].strip())
            parts.append("")
    return "\n".join(parts) + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "NOTICE.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"NOTICE écrit : {out} ({out.stat().st_size} octets)")


if __name__ == "__main__":
    main()
