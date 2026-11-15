# PyInstaller 6, mode --onedir : deux exécutables (Voxpage.exe fenêtré, voxpage-cli.exe console) dans un
# même dossier, partageant le même _internal/.  Build : pyinstaller packaging/voxpage.spec
# (depuis la racine du dépôt). Pas d'UPX : faux positifs antivirus.
import subprocess
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parent  # noqa: F821  (SPECPATH est fourni par PyInstaller)
PKG = ROOT / "packaging"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

# --- Icône (générée avec Pillow si absente) --------------------------------------------------------
ICON = PKG / "voxpage.ico"
if not ICON.is_file():
    subprocess.run([sys.executable, str(PKG / "make_icon.py"), str(ICON)], check=True)

# --- Bibliothèques natives et données --------------------------------------------------------------
datas, binaries, hiddenimports = [], [], []

# sherpa-onnx : _sherpa_onnx.pyd + lib/ (onnxruntime.dll, sherpa-onnx-c-api.dll, ...)
for pkg in ("sherpa_onnx",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# pypdfium2 : pdfium.dll (pypdfium2_raw) et fichiers de version lus à l'import
for pkg in ("pypdfium2", "pypdfium2_raw"):
    datas += collect_data_files(pkg)
    binaries += collect_dynamic_libs(pkg)
    hiddenimports += collect_submodules(pkg)

# lameenc : extension native
binaries += collect_dynamic_libs("lameenc")
hiddenimports += ["lameenc"]

# pdfminer : tables CMap (pickle.gz) lues dynamiquement
datas += collect_data_files("pdfminer")
hiddenimports += collect_submodules("pdfminer")

# num2words : un module par langue, importé dynamiquement
datas += collect_data_files("num2words")
hiddenimports += collect_submodules("num2words")

# wxPython : le hook fourni par PyInstaller gère wx ; on s'assure des modules utilisés
hiddenimports += ["wx", "wx.adv"]

# Paquets du projet chargés par nom
hiddenimports += collect_submodules("voxpage")

EXCLUDES = [
    "tkinter", "unittest", "pytest", "test", "tests", "pydoc", "doctest", "distutils", "setuptools",
    "pip", "IPython", "matplotlib", "scipy", "pandas", "PyInstaller",
]

a = Analysis(  # noqa: F821
    [str(PKG / "entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821


def _version_info(filename: str, description: str) -> VSVersionInfo:
    parts = [int(x) for x in VERSION.split(".")[:3]]
    parts += [0] * (4 - len(parts))
    tup = tuple(parts)
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=tup, prodvers=tup, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
        kids=[
            StringFileInfo([StringTable("040C04B0", [
                StringStruct("CompanyName", "Voxpage"),
                StringStruct("FileDescription", description),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", filename),
                StringStruct("LegalCopyright", "Voxpage"),
                StringStruct("OriginalFilename", filename),
                StringStruct("ProductName", "Voxpage"),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
        ],
    )


def _exe(name: str, console: bool, description: str):
    return EXE(  # noqa: F821
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,  # mode onedir
        name=name,
        console=console,
        icon=str(ICON),
        version=_version_info(name + ".exe", description),
        upx=False,
        debug=False,
        strip=False,
    )


gui = _exe("Voxpage", False, "Voxpage : convertit un document en audio")
cli = _exe("voxpage-cli", True, "Voxpage en ligne de commande")

coll = COLLECT(  # noqa: F821
    gui,
    cli,
    a.binaries,
    a.datas,
    upx=False,
    name="Voxpage",
)
