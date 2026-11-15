"""Teste le zip portable tel qu'il sera livré (à lancer sous Windows, après packaging/assemble.py).

Usage : python packaging/test_release.py dist/Voxpage-X.Y.Z-win64-portable.zip

Le zip est décompressé hors du dépôt, dans un chemin avec espace et accent ; les exécutables tournent
avec un environnement Python vidé et un PATH réduit à Windows (aucune DLL de la machine de build).
"""

import base64
import locale
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from mutagen import File as MutagenFile

ROOT = Path(__file__).resolve().parent.parent
FR_TEXT = (
    "Bonjour. Ceci est un court texte de test pour vérifier la synthèse vocale de Voxpage. "
    "Le chat dort sur le canapé, et il y a 12 pommes dans le panier. "
    "La lecture doit durer quelques secondes seulement."
)
EN_TEXT = "Hello. This is a short test of the English voice. The cat sleeps on the sofa."
VOICES = ["fr_FR-siwis-medium", "fr_FR-upmc-medium", "en_GB-cori-medium"]
failures: list[str] = []


def fail(msg: str) -> None:
    print(f"ECHEC : {msg}", flush=True)
    failures.append(msg)


def ok(msg: str) -> None:
    print(f"ok : {msg}", flush=True)


def clean_env() -> dict[str, str]:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "VIRTUAL_ENV"))}
    env["PATH"] = rf"{root}\System32;{root}"
    return env


def run(exe: Path, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    print(f"$ {exe.name} {' '.join(args)}", flush=True)
    proc = subprocess.run(
        [str(exe), *args], capture_output=True, timeout=timeout, env=clean_env(), cwd=exe.parent.parent
    )
    # les exécutables écrivent dans l'encodage de la console de la machine (cp1252 ici)
    enc = locale.getpreferredencoding(False)
    proc.stdout_text = proc.stdout.decode(enc, "replace")  # type: ignore[attr-defined]
    proc.stderr_text = proc.stderr.decode(enc, "replace")  # type: ignore[attr-defined]
    return proc


def tree(base: Path) -> set[str]:
    return {str(p.relative_to(base)) for p in base.rglob("*")} if base.exists() else set()


def traces() -> dict[str, set[str]]:
    """Dossiers « Voxpage » ou « _MEI* » sous le profil et le dossier temporaire (profondeur 2)."""
    found: dict[str, set[str]] = {}
    for var in ("APPDATA", "LOCALAPPDATA", "TEMP", "USERPROFILE"):
        base = Path(os.environ.get(var, ""))
        hits: set[str] = set()
        if base.is_dir():
            for pattern in ("*", "*/*"):
                for p in base.glob(pattern):
                    if re.search(r"voxpage|^_MEI", p.name, re.I):
                        hits.add(str(p))
        found[var] = hits
    return found


def duration(path: Path) -> float:
    f = MutagenFile(path)
    return float(f.info.length) if f is not None else 0.0


def convert(exe: Path, src: Path, out: Path, label: str, *args: str, lo: float, hi: float) -> None:
    p = run(exe, str(src), "-o", str(out), "--silencieux", *args)
    if p.returncode != 0:
        fail(f"{label} : code {p.returncode}\n{p.stderr_text}")
        return
    if not out.is_file() or out.stat().st_size == 0:
        fail(f"{label} : fichier absent ou vide ({out})")
        return
    d = duration(out)
    if lo <= d <= hi:
        ok(f"{label} : {d:.1f} s, {out.stat().st_size} octets")
    else:
        fail(f"{label} : durée {d:.1f} s hors de [{lo}, {hi}]")


def flat(text: str) -> str:
    """Texte comparable : apostrophes et guillemets unifiés, espaces ramenés à un, minuscules."""
    table = {ord(c): "'" for c in "’‘"} | {ord(c): '"' for c in "“”«»"} | {ord(c): "-" for c in "–—"}
    table |= {ord(c): " " for c in "\u00a0\u202f"}
    text = text.translate(table)
    return re.sub(r"\s+", " ", text).strip().lower()


def export_text(exe: Path, src: Path, out: Path, label: str, phrases: list[str], *args: str,
                forbidden: tuple[str, ...] = (), stderr_has: str | None = None) -> str:
    """Exporte le texte lu (--texte) et vérifie qu'il contient (ou ne contient pas) des phrases."""
    p = run(exe, str(src), "--texte", str(out), *args)
    if p.returncode != 0 or not out.is_file():
        fail(f"{label} : code {p.returncode}\n{p.stderr_text}")
        return ""
    text = out.read_text(encoding="utf-8")
    body = flat(text)
    missing = [s for s in phrases if flat(s) not in body]
    present = [s for s in forbidden if flat(s) in body]
    if missing or present:
        fail(f"{label} : phrases absentes {missing}, phrases indésirables {present}\n--- texte ---\n{text}")
    elif stderr_has is not None and stderr_has not in p.stderr_text:
        fail(f"{label} : avertissement attendu absent ({stderr_has!r}) : {p.stderr_text!r}")
    else:
        ok(f"{label} : texte exporté conforme ({len(text)} caractères)")
    return text


def block_network(*exes: Path) -> None:
    """Règle de pare-feu sortante bloquant les exécutables (échec toléré : simple garde-fou)."""
    for exe in exes:
        cmd = (
            f"New-NetFirewallRule -DisplayName 'voxpage-test-{exe.name}' -Direction Outbound "
            f"-Action Block -Program '{exe.resolve()}' | Out-Null"
        )
        encoded = base64.b64encode(cmd.encode("utf-16-le")).decode("ascii")
        p = subprocess.run(
            ["powershell", "-NoProfile", "-EncodedCommand", encoded], capture_output=True, text=True
        )
        print(
            f"pare-feu {exe.name} : {'bloqué' if p.returncode == 0 else 'non appliqué ' + p.stderr.strip()}"
        )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    zip_path = Path(sys.argv[1]).resolve()
    base = Path(tempfile.mkdtemp(prefix="Essai é ")) / "Dossier avec espace"
    base.mkdir()
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(base)
    app = base / "Voxpage"
    out_dir = base / "sortie é"
    out_dir.mkdir()
    gui, cli = app / "Voxpage.exe", app / "voxpage-cli.exe"
    print(f"Application décompressée dans : {app}")
    if ROOT in app.parents:
        fail("l'application ne doit pas être décompressée dans le dépôt")

    before_traces, before_app = traces(), tree(app)
    block_network(gui, cli)

    # Version et voix
    p = run(cli, "--version")
    m = re.search(r"voxpage (\S+)", p.stdout_text)
    expected = re.search(r"-(\d+\.\d+\.\d+)-win64", zip_path.name)
    if p.returncode == 0 and m and expected and m.group(1) == expected.group(1):
        ok(f"--version : {m.group(1)}")
    else:
        fail(f"--version : {p.returncode} {p.stdout_text!r} {p.stderr_text!r}")
    p = run(cli, "--liste-voix")
    missing = [v for v in VOICES if v not in p.stdout_text]
    if p.returncode == 0 and not missing:
        ok("--liste-voix : les 3 voix sont présentes")
    else:
        fail(f"--liste-voix : code {p.returncode}, absentes {missing}\n{p.stdout_text}{p.stderr_text}")

    # Diagnostic : dossiers, réglages, bibliothèques natives et données embarquées
    p = run(cli, "--diagnostic")
    print(p.stdout_text)
    fields = dict(line.split("=", 1) for line in p.stdout_text.splitlines() if re.match(r"\w+=", line))
    if p.returncode == 0 and "ÉCHEC" not in p.stdout_text and "ok ocr : lu" in p.stdout_text:
        ok("--diagnostic : bibliothèques et données présentes, moteur OCR chargé")
    else:
        fail(f"--diagnostic : code {p.returncode}\n{p.stderr_text}")
    if fields.get("frozen") != "True" or Path(fields.get("app_dir", "")).resolve() != app.resolve():
        fail(f"app_dir incorrect : {fields}")
    if (
        Path(fields.get("settings", "")).resolve() != (app / "settings.json").resolve()
        or not (app / "settings.json").is_file()
    ):
        fail(f"settings.json non écrit à côté de l'exécutable : {fields.get('settings')}")
    else:
        ok("settings.json écrit à côté de l'exécutable")

    # Conversions
    fr = base / "texte français.txt"
    fr.write_text(FR_TEXT, encoding="utf-8")
    en = base / "english text.txt"
    en.write_text(EN_TEXT, encoding="utf-8")
    convert(cli, fr, out_dir / "siwis.mp3", "siwis MP3", "--voix", "fr_FR-siwis-medium", lo=4, hi=60)
    convert(
        cli,
        fr,
        out_dir / "siwis.wav",
        "siwis WAV",
        "--voix",
        "fr_FR-siwis-medium",
        "--format",
        "wav",
        lo=4,
        hi=60,
    )
    for n, who in ((0, "Jessica"), (1, "Pierre")):
        convert(
            cli,
            fr,
            out_dir / f"upmc{n}.mp3",
            f"upmc {who} MP3",
            "--voix",
            "fr_FR-upmc-medium",
            "--locuteur",
            str(n),
            lo=4,
            hi=60,
        )
    convert(
        cli,
        fr,
        out_dir / "upmc.wav",
        "upmc WAV",
        "--voix",
        "fr_FR-upmc-medium",
        "--format",
        "wav",
        lo=4,
        hi=60,
    )
    convert(cli, en, out_dir / "cori.mp3", "cori MP3", "--voix", "en_GB-cori-medium", lo=2, hi=40)
    # Voxpage.exe (fenêtré) avec arguments : délègue à la CLI
    convert(
        gui,
        fr,
        out_dir / "via-gui.mp3",
        "Voxpage.exe + arguments",
        "--voix",
        "fr_FR-siwis-medium",
        lo=4,
        hi=60,
    )

    # Texte exporté : PDF natif, puis PDF scanné lu par OCR (moteur et modèles livrés dans le zip)
    corpus = ROOT / "tests" / "corpus"
    for name in ("ch_PP-OCRv5_det_mobile.onnx", "latin_PP-OCRv5_rec_mobile.onnx"):
        if (app / "ocr" / name).is_file():
            ok(f"ocr/{name} présent")
        else:
            fail(f"ocr/{name} absent du zip")
    export_text(
        cli, corpus / "simple.pdf", base / "natif.txt", "texte du PDF natif",
        ["Le phare de Kerbrat se dresse à la pointe d’un cap battu par les vents.",
         "Le gardien, Yves Le Goff, monte chaque soir les cent douze marches"],
        forbidden=("OCR",),
    )
    scan_phrases = [
        "Cette première page contient du texte natif.",
        "Compte rendu du conseil",
        "Le conseil municipal s’est réuni le 14 mars",
        "la rénovation de l’école Jules-Ferry",
        "a déclaré la maire, Hélène Garnier.",
    ]
    export_text(
        cli, corpus / "scan.pdf", base / "scanné.txt", "texte du PDF scanné (OCR)", scan_phrases,
        stderr_has="reconnu par OCR",
    )
    export_text(
        cli, corpus / "scan.pdf", base / "sans-ocr.txt", "PDF scanné avec --ocr jamais",
        ["Cette première page contient du texte natif."], "--ocr", "jamais",
        forbidden=("conseil municipal",), stderr_has="aucun texte exploitable",
    )
    # Conversion audio du PDF scanné : OCR (onnxruntime) puis synthèse (sherpa-onnx) dans le même processus
    convert(
        cli, corpus / "scan.pdf", out_dir / "scanné.mp3", "PDF scanné → MP3", "--voix", "fr_FR-siwis-medium",
        lo=5, hi=120,
    )

    # PDF du corpus, s'il existe
    pdfs = sorted(corpus.glob("*.pdf"))[:3]
    if not pdfs:
        print("PDF du corpus : tests/corpus/ absent ou vide, étape sautée")
    for pdf in pdfs:
        convert(
            cli,
            pdf,
            out_dir / f"{pdf.stem}.mp3",
            f"PDF {pdf.name}",
            "--voix",
            "fr_FR-siwis-medium",
            lo=1,
            hi=3600,
        )

    # Interface graphique : auto-test (le sous-système fenêtré n'a pas de console, seul le code compte)
    p = run(gui, "--gui-self-test", timeout=300)
    if p.returncode == 0:
        ok("Voxpage.exe --gui-self-test : code 0")
    else:
        fail(f"Voxpage.exe --gui-self-test : code {p.returncode}")
        print(run(cli, "--gui-self-test", timeout=300).stdout_text)

    # Portabilité : rien hors du dossier de l'application et du dossier de sortie
    after_traces, after_app = traces(), tree(app)
    for var, hits in after_traces.items():
        new = hits - before_traces[var]
        if new:
            fail(f"fichiers créés hors du dossier de l'application ({var}) : {sorted(new)}")
    unexpected = (after_app - before_app) - {"settings.json"}
    if unexpected:
        fail(f"fichiers inattendus dans le dossier de l'application : {sorted(unexpected)[:10]}")
    if not failures:
        ok("aucune écriture hors du dossier de l'application et du dossier de sortie")

    print(f"\n{len(failures)} échec(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
