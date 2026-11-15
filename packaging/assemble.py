"""Complète le dossier produit par PyInstaller et crée le zip portable.

Usage : python packaging/assemble.py [dist/Voxpage]
  - copie voices/ (voix + README), LISEZMOI.txt et NOTICE.txt à côté des exécutables ;
  - retire les fichiers parasites (caches, tests) ;
  - écrit dist/Voxpage-<version>-win64-portable.zip et le .sha256 correspondant.
"""

import hashlib
import shutil
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
TOP = "Voxpage"  # dossier racine dans le zip
PARASITES = ("__pycache__", "tests", "test")


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def prune(app: Path) -> int:
    removed = 0
    for path in sorted(app.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.exists():
            continue
        if path.is_dir() and path.name in PARASITES and "voices" not in path.relative_to(app).parts:
            shutil.rmtree(path)
            removed += 1
        elif path.is_file() and path.suffix in (".pyc", ".pyo"):
            path.unlink()
            removed += 1
    return removed


def main() -> None:
    app = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / TOP
    for exe in ("Voxpage.exe", "voxpage-cli.exe"):
        if not (app / exe).is_file():
            raise SystemExit(f"{exe} absent de {app} : le build PyInstaller a-t-il réussi ?")
    voices = ROOT / "voices"
    if len(list(voices.glob("*/voice.json"))) != 3:
        raise SystemExit("Les trois voix doivent être présentes dans voices/ (python tools/fetch_voices.py).")
    shutil.copytree(voices, app / "voices", dirs_exist_ok=True)
    shutil.copy2(PKG / "LISEZMOI.txt", app / "LISEZMOI.txt")
    notice = ROOT / "build" / "NOTICE.txt"
    if not notice.is_file():
        raise SystemExit("build/NOTICE.txt absent (python packaging/make_notice.py build/NOTICE.txt).")
    shutil.copy2(notice, app / "NOTICE.txt")
    print(f"Fichiers parasites retirés : {prune(app)}")

    name = f"Voxpage-{version()}-win64-portable"
    zip_path = app.parent / f"{name}.zip"
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                z.write(path, f"{TOP}/{path.relative_to(app).as_posix()}")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    zip_path.with_name(zip_path.name + ".sha256").write_text(f"{digest} *{zip_path.name}\n", encoding="utf-8")
    print(f"{zip_path} : {zip_path.stat().st_size / 1e6:.1f} Mo, sha256 {digest}")


if __name__ == "__main__":
    main()
