#!/usr/bin/env python3
"""Banc d'essai OCR : fidélité en français, par moteur et par condition de numérisation.

Usage (dans le conteneur d'évaluation, voir docs/ocr.md) :
  python tools/ocr_bench.py gen   DOSSIER            # pages de vérité terrain + variantes dégradées
  python tools/ocr_bench.py run   DOSSIER MOTEUR...  # mesure ; ex. tesseract-best rapidocr-v5 voxpage
  python tools/ocr_bench.py fetch-real DOSSIER       # pages réelles du domaine public (Wikisource)

Les pages sont rendues à partir de textes français connus (tools/ocr_bench_texts.py et deux pages de la
Constitution du corpus), à 300 dpi, puis dégradées de façon reproductible (graine fixe) :

  propre-300   rendu net à 300 dpi
  propre-150   même page à 150 dpi
  mauvais-300  flou, bruit, contraste faible, éclairage inégal, rotation 1,5°, JPEG q45
  mauvais-150  idem à 150 dpi
  incline-300  rotation de -2° seule, JPEG q70

Mesures : taux d'erreur de caractères (CER) et de mots (WER) sur le texte aplati (retours à la ligne
ramenés à une espace ; apostrophes, guillemets et tirets ramenés à une forme commune car la synthèse
vocale les lit de la même façon), erreurs d'accent (opérations d'édition touchant une lettre accentuée) et
d'espacement (opérations touchant une espace), pour 1 000 caractères, et temps par page.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CONDITIONS = ["propre-300", "propre-150", "mauvais-300", "mauvais-150", "incline-300"]
PAGE_W, PAGE_H = 595.0, 842.0  # A4, points


# ---------------------------------------------------------------------------------------------------------
# Génération


def _wrap(words: list[str], font: str, size: float, width: float) -> list[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if stringWidth(trial, font, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_text_pdf(spec: dict, path: Path) -> str:
    """Écrit le PDF de la page et renvoie la vérité terrain (texte aplati)."""
    from reportlab.pdfgen import canvas

    font, size = spec["font"], spec["size"]
    cols = spec.get("columns", 1)
    margin, gutter = 72.0, 24.0
    col_w = (PAGE_W - 2 * margin - gutter * (cols - 1)) / cols
    lead = size * 1.35
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    y_top = PAGE_H - 80
    truth: list[str] = []
    if spec.get("title"):
        bold = {"Times-Roman": "Times-Bold", "Helvetica": "Helvetica-Bold"}.get(font, font)
        c.setFont(bold, size + 4)
        c.drawString(margin, y_top, spec["title"])
        truth.append(spec["title"])
        y_top -= (size + 4) * 2.2
    col, y = 0, y_top
    c.setFont(font, size)
    for para in spec["paragraphs"]:
        truth.append(para)
        for line in _wrap(para.split(), font, size, col_w):
            if y < 80:
                col, y = col + 1, y_top
            x = margin + col * (col_w + gutter)
            c.setFont(font, size)
            c.drawString(x, y, line)
            y -= lead
        y -= lead * 0.5
    c.save()
    return "\n\n".join(truth)


def real_pdf_pages() -> list[tuple[dict, str]]:
    """Pages dont le texte vient du corpus réel (Constitution), lu avec l'extracteur de Voxpage."""
    from ocr_bench_texts import REAL_PDF_PAGES

    from voxpage.extract import ExtractOptions, extractor_for

    path = ROOT / "tests" / "corpus" / "reels" / "constitution-1958.pdf"
    out = []
    for ident, start, font, size in REAL_PDF_PAGES:
        doc = extractor_for(path).extract(path, ExtractOptions(pages=f"{start}-{start + 2}"))
        paras, total = [], 0
        for ch in doc.chapters:
            for b in ch.blocks:
                if b.kind == "paragraph" and len(b.text) > 40:
                    paras.append(b.text)
                    total += len(b.text)
                if total > 2300:
                    break
        out.append(({"id": ident, "font": font, "size": size, "title": "", "paragraphs": paras}, ""))
    return out


def degrade(img, condition: str, seed: int):
    """Applique la dégradation `condition` (image PIL en niveaux de gris, 300 dpi)."""
    import io

    import numpy as np
    from PIL import Image, ImageFilter

    rng = np.random.default_rng(seed)
    dpi = 150 if condition.endswith("150") else 300
    kind = condition.split("-")[0]
    if dpi == 150:
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    if kind == "propre":
        return img
    if kind == "incline":
        img = img.rotate(-2.0, resample=Image.BICUBIC, fillcolor=255, expand=False)
        quality = 70
    else:
        scale = 1.0 if dpi == 300 else 0.5
        img = img.rotate(1.5, resample=Image.BICUBIC, fillcolor=255, expand=False)
        img = img.filter(ImageFilter.GaussianBlur(radius=1.1 * scale if dpi == 300 else 0.7))
        a = np.asarray(img, dtype=np.float32)
        a = 95 + a * (170 - 95) / 255  # contraste faible : noir à 95, blanc à 170
        h, w = a.shape
        yy, xx = np.mgrid[0:h, 0:w]
        a = a * (0.82 + 0.18 * (xx / w * 0.6 + yy / h * 0.4))  # éclairage inégal
        a = a + rng.normal(0, 10, a.shape)  # bruit
        specks = rng.random(a.shape) < 0.0008
        a[specks] = 40
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L")
        quality = 45
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("L")


def cmd_gen(out: Path) -> None:
    import pypdfium2 as pdfium
    from ocr_bench_texts import TEXTS

    specs: list[tuple[dict, str]] = [(t, "") for t in TEXTS] + real_pdf_pages()
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for n, (spec, _) in enumerate(specs):
        pdf = out / f"{spec['id']}.src.pdf"
        truth = render_text_pdf(spec, pdf)
        (out / f"{spec['id']}.txt").write_text(truth, encoding="utf-8")
        doc = pdfium.PdfDocument(str(pdf))
        base = doc[0].render(scale=300 / 72, grayscale=True).to_pil().convert("L")
        doc.close()
        for cond in CONDITIONS:
            img = degrade(base, cond, seed=1000 * n + CONDITIONS.index(cond))
            dpi = 150 if cond.endswith("150") else 300
            name = f"{spec['id']}.{cond}"
            img.save(out / f"{name}.png", dpi=(dpi, dpi))
            img.save(out / f"{name}.pdf", "PDF", resolution=dpi)  # page « scannée » : une image seule
            manifest.append({"id": spec["id"], "condition": cond, "truth": f"{spec['id']}.txt"})
        pdf.unlink()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"{len(specs)} pages x {len(CONDITIONS)} conditions dans {out}")


# ---------------------------------------------------------------------------------------------------------
# Mesures

_FOLD = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "“": '"', "”": '"', "«": '"', "»": '"',
                       "–": "-", "—": "-", "−": "-", " ": " ", " ": " "})


def flatten(text: str, fold: bool = True) -> str:
    text = unicodedata.normalize("NFC", text)
    if fold:
        text = text.translate(_FOLD)
        text = re.sub(r'\s*"\s*', '"', text)  # « texte » / "texte" : espaces autour sans objet
        # espace avant la ponctuation haute : sans effet à l'oral
        text = re.sub(r"\s+([!?;:%€°])", r"\1", text)
        text = re.sub(r"\s*-\s+", "- ", text)
    return re.sub(r"\s+", " ", text).strip()


def _lev():
    try:
        from rapidfuzz.distance import Levenshtein

        return Levenshtein
    except ImportError:  # pragma: no cover
        return None


def edit_ops(ref: str, hyp: str):
    L = _lev()
    if L is None:
        raise SystemExit("rapidfuzz est nécessaire au banc (pip install rapidfuzz)")
    return L.opcodes(ref, hyp)


def assemble(raw: str) -> str:
    """Texte brut d'un moteur → texte continu, césures de fin de ligne recollées comme le fait Voxpage
    (mêmes règles que l'extracteur) : la comparaison porte sur la lecture, pas sur la mise en lignes."""
    from voxpage.extract.pdf_text import WordStats, join_lines

    lines = [ln.strip() for ln in raw.splitlines()]
    stats = WordStats()
    for ln in lines:
        stats.add_line(ln)
    out: list[str] = []
    for chunk in re.split(r"\n\s*\n", raw):
        cur = ""
        for ln in (x.strip() for x in chunk.splitlines()):
            cur = join_lines(cur, ln, stats) if cur else ln
        out.append(cur)
    return "\n\n".join(out)


def score(truth: str, hyp: str) -> dict:
    ref, got = flatten(truth), flatten(assemble(hyp))
    L = _lev()
    cer = L.distance(ref, got) / max(1, len(ref))
    rw, gw = ref.split(" "), got.split(" ")
    wer = L.distance(rw, gw) / max(1, len(rw))
    ref_s, got_s = flatten(truth, False), flatten(assemble(hyp), False)
    cer_strict = L.distance(ref_s, got_s) / max(1, len(ref_s))
    accent = space = 0
    for op in edit_ops(ref, got):
        if op.tag == "equal":
            continue
        a, b = ref[op.src_start : op.src_end], got[op.dest_start : op.dest_end]
        if any(ch.isalpha() and not ch.isascii() for ch in a + b):
            accent += 1
        if " " in a or " " in b:
            space += 1
    k = 1000 / max(1, len(ref))
    return {"cer": cer, "wer": wer, "cer_strict": cer_strict, "accent_err": accent * k,
            "space_err": space * k, "chars": len(ref)}


# ---------------------------------------------------------------------------------------------------------
# Moteurs : chaque moteur est un objet avec .read(image_path) -> texte (lignes dans l'ordre de lecture)


class Tesseract:
    def __init__(self, tessdata: str, psm: int = 3, lang: str = "fra"):
        self.tessdata, self.psm, self.lang = tessdata, psm, lang

    def read(self, image: Path) -> str:
        cmd = ["tesseract", str(image), "stdout", "-l", self.lang, "--oem", "1", "--psm", str(self.psm),
               "--tessdata-dir", self.tessdata]
        return subprocess.run(cmd, capture_output=True, check=True, timeout=300).stdout.decode("utf-8")


class RapidOcr:
    """RapidOCR (onnxruntime). Réglages communs : aucun seuil de confiance (rien n'est écarté), pas de
    classifieur d'orientation, pas de réduction interne de l'image."""

    def __init__(self, version: str, det: str, rec: str, rec_type: str, det_lang: str = "multi",
                 model_dir: str | None = None, tune: dict | None = None):
        from rapidocr import ModelType, OCRVersion, RapidOCR

        tune = tune or {}
        ver, det_t, rec_t = OCRVersion(version), ModelType(det), ModelType(rec_type)
        params = {
            "Det.ocr_version": ver, "Det.model_type": det_t, "Det.lang_type": det_lang,
            "Rec.ocr_version": ver, "Rec.model_type": rec_t, "Rec.lang_type": rec,
            "Global.log_level": "warning", "Global.text_score": 0.0, "Global.use_cls": False,
            "Global.max_side_len": 20000, "Global.min_side_len": 1,
        }
        if model_dir:
            params["Global.model_root_dir"] = model_dir
        names = {"lim": "Det.limit_side_len", "unclip": "Det.unclip_ratio", "dil": "Det.use_dilation",
                 "thresh": "Det.thresh", "box": "Det.box_thresh", "batch": "Rec.rec_batch_num"}
        for key, val in tune.items():
            if key in names:
                params[names[key]] = val
        if "lim" in tune:
            params["Det.limit_type"] = "max"
        self.long_side = tune.get("long")
        self.engine = RapidOCR(params=params)

    def read(self, image: Path) -> str:
        import numpy as np
        from PIL import Image

        img = Image.open(image).convert("RGB")
        if self.long_side and max(img.size) > self.long_side:
            k = self.long_side / max(img.size)
            img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
        res = self.engine(np.asarray(img))
        if res.boxes is None:
            return ""
        return lines_from_boxes(list(res.boxes), list(res.txts))


def _parse_tune(spec: str) -> dict:
    out: dict = {}
    for item in spec.split(","):
        if not item:
            continue
        k, v = item.split("=")
        if v in ("True", "False"):
            out[k] = v == "True"
        else:
            out[k] = float(v) if "." in v else int(v)
    return out


def lines_from_boxes(boxes, txts) -> str:
    """Remet les boîtes détectées dans l'ordre de lecture (lignes puis x) — suffisant pour une colonne."""
    items = []
    for box, txt in zip(boxes, txts, strict=False):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append((min(ys), max(ys), min(xs), txt))
    items.sort(key=lambda t: (t[0] + t[1]) / 2)
    rows: list[list] = []
    for it in items:
        mid = (it[0] + it[1]) / 2
        if rows and abs(mid - (rows[-1][0][0] + rows[-1][0][1]) / 2) < 0.5 * (it[1] - it[0]):
            rows[-1].append(it)
        else:
            rows.append([it])
    return "\n".join(" ".join(t[3] for t in sorted(r, key=lambda t: t[2])) for r in rows)


from voxpage.extract.ocr_prep import prepare  # noqa: E402


class Prepped:
    """Moteur précédé du prétraitement de Voxpage (fond uniformisé, redressement)."""

    def __init__(self, inner):
        self.inner = inner

    def read(self, image: Path) -> str:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "p.png"
            prepare(Image.open(image).convert("L")).save(out)
            return self.inner.read(out)


def make_engine(name: str, args):
    if name.endswith("+norm"):
        return Prepped(make_engine(name[:-5], args))
    tess = args.tessdata
    if name == "tesseract-best":
        return Tesseract(f"{tess}/best")
    if name == "tesseract-fast":
        return Tesseract(f"{tess}/fast")
    if name == "tesseract-best-psm6":
        return Tesseract(f"{tess}/best", psm=6)
    if name.startswith("rapidocr-"):
        name, _, tune_spec = name.partition("@")
        table = {
            "rapidocr-v6-small": ("PP-OCRv6", "small", "fr", "small"),
            "rapidocr-v6-medium": ("PP-OCRv6", "medium", "fr", "medium"),
            "rapidocr-v6-tiny": ("PP-OCRv6", "tiny", "fr", "tiny"),
            "rapidocr-v5": ("PP-OCRv5", "mobile", "latin", "mobile"),
            "rapidocr-v5-server": ("PP-OCRv5", "server", "latin", "mobile"),
            "rapidocr-v4": ("PP-OCRv4", "mobile", "latin", "mobile"),
        }
        v, det, rec, rec_t = table[name]
        return RapidOcr(v, det, rec, rec_t, det_lang="fr" if v == "PP-OCRv6" else "multi",
                        model_dir=args.models, tune=_parse_tune(tune_spec))
    if name == "voxpage":
        return VoxpageEngine()
    raise SystemExit(f"moteur inconnu : {name}")


class VoxpageEngine:
    """Chaîne complète de Voxpage : extracteur PDF en mode OCR sur le PDF « scanné » de la même page ;
    le texte lu est celui des blocs (paragraphes séparés par une ligne vide)."""

    def read(self, image: Path) -> str:
        from voxpage.extract import ExtractOptions, extractor_for

        pdf = image.with_suffix(".pdf")
        doc = extractor_for(pdf).extract(pdf, ExtractOptions(ocr="always"))
        return "\n\n".join(b.text for ch in doc.chapters for b in ch.blocks)


def cmd_run(folder: Path, engines: list[str], args) -> None:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    only = set(args.only.split(",")) if args.only else None
    results = {}
    for name in engines:
        eng = make_engine(name, args)
        eng.read(folder / f"{manifest[0]['id']}.{manifest[0]['condition']}.png")  # échauffement
        per_cond: dict[str, list[dict]] = {}
        for item in manifest:
            if only and item["id"] not in only:
                continue
            if args.cond and item["condition"] not in args.cond.split(","):
                continue
            img = folder / f"{item['id']}.{item['condition']}.png"
            truth = (folder / item["truth"]).read_text(encoding="utf-8")
            t0 = time.perf_counter()
            text = eng.read(img)
            dt = time.perf_counter() - t0
            m = score(truth, text)
            m["seconds"] = dt
            m["page"] = item["id"]
            per_cond.setdefault(item["condition"], []).append(m)
            if args.verbose:
                print(f"  {name:22} {item['id']:16} {item['condition']:12} "
                      f"CER {m['cer']:.2%} WER {m['wer']:.2%} {dt:.1f}s", flush=True)
        results[name] = per_cond
        print(f"== {name}", flush=True)
        for cond, rows in per_cond.items():
            print("  " + summary_line(cond, rows), flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1), encoding="utf-8")


def mean(rows, key):
    return sum(r[key] for r in rows) / len(rows)


def summary_line(cond: str, rows: list[dict]) -> str:
    # moyenne pondérée par le nombre de caractères pour CER/WER serait plus fidèle ; moyenne simple ici
    return (f"{cond:12} CER {mean(rows, 'cer'):6.2%}  WER {mean(rows, 'wer'):6.2%}  "
            f"accents {mean(rows, 'accent_err'):5.1f}  espaces {mean(rows, 'space_err'):5.1f}  "
            f"{mean(rows, 'seconds'):5.1f} s/page  (n={len(rows)})")


# ---------------------------------------------------------------------------------------------------------
# Pages réelles (Wikisource) : texte relu par la communauté en face de l'image numérisée

REAL_BOOKS = [  # (fichier Commons, plage de pages candidates)
    ("Daudet - Aventures prodigieuses de Tartarin de Tarascon, 1872.djvu", range(30, 200)),
    ("Flaubert - Bouvard et Pécuchet, éd. Conard, 1910.djvu", range(40, 400)),
    ("Zola - Contes à Ninon, 1864.djvu", range(20, 300)),
    ("Verne - Autour de la Lune.djvu", range(20, 100)),
]
UA = {"User-Agent": "voxpage-ocr-bench/1.0 (banc d'essai OCR, https://github.com/aldryss/voxpage)"}


def _api(**params):
    import urllib.parse
    import urllib.request

    params["format"] = "json"
    url = "https://fr.wikisource.org/w/api.php?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def clean_wikitext(raw: str) -> str | None:
    """Texte brut d'une page Wikisource de niveau « validé », ou None si la page n'est pas simple (modèles,
    notes, pied de page, vers...). Un en-tête courant `{{nr|numéro|titre|...}}` est ajouté en tête du texte :
    il est imprimé sur la page, l'OCR le lit."""
    import html

    if 'pagequality level="4"' not in raw:
        return None
    outside = re.sub(r"<noinclude>.*?</noinclude>", "", raw, flags=re.S)
    inside = "".join(re.findall(r"<noinclude>(.*?)</noinclude>", raw, flags=re.S))
    inside = re.sub(r"<pagequality[^>]*/>|<references\s*/>", "", inside).strip()
    header = re.fullmatch(r"\{\{nr\|([^{}]*)\}\}", inside)
    if inside and not header:  # pied de page, modèles divers : page écartée
        return None
    text = re.sub(r"''+", "", outside)
    text = html.unescape(text)
    if re.search(r"\{\{|<|\[\[|\|", text):
        return None
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    if header:
        parts = [x.strip() for x in header.group(1).split("|") if x.strip() and "=" not in x]
        text = " ".join(parts) + "\n\n" + text
    return text if 700 <= len(text) <= 3200 else None


def cmd_fetch_real(folder: Path, per_book: int = 3) -> None:  # pragma: no cover — réseau
    import urllib.request

    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else []
    manifest = [m for m in manifest if m["condition"] != "reel"]
    for filename, pages in REAL_BOOKS:
        kept, taken = 0, -100
        numbers = list(pages)
        for i in range(0, len(numbers), 40):
            if kept >= per_book:
                break
            batch = numbers[i : i + 40]
            titles = "|".join(f"Page:{filename}/{n}" for n in batch)
            data = _api(action="query", prop="revisions", rvprop="content", rvslots="main", titles=titles)
            found = {}
            for pg in data["query"]["pages"].values():
                if "revisions" in pg:
                    found[int(pg["title"].rsplit("/", 1)[1])] = pg["revisions"][0]["slots"]["main"]["*"]
            for n in sorted(found):
                text = clean_wikitext(found[n])
                if text is None or kept >= per_book or n < taken + 12:
                    continue
                taken = n
                info = _api(action="query", prop="imageinfo", iiprop="url", iiurlparam=f"page{n}-1900px",
                            titles=f"File:{filename}")
                url = list(info["query"]["pages"].values())[0]["imageinfo"][0]["thumburl"]
                ident = "reel-" + re.sub(r"\W+", "-", filename.split(" - ")[0].lower()) + f"-{n}"
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                    (folder / f"{ident}.reel.jpg").write_bytes(r.read())
                _jpg_to_files(folder, ident)
                (folder / f"{ident}.txt").write_text(text, encoding="utf-8")
                manifest.append({"id": ident, "condition": "reel", "truth": f"{ident}.txt"})
                kept += 1
                print(f"{ident} : {len(text)} caractères")
                time.sleep(1)
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def _jpg_to_files(folder: Path, ident: str) -> None:
    from PIL import Image

    jpg = folder / f"{ident}.reel.jpg"
    img = Image.open(jpg).convert("L")
    img.save(folder / f"{ident}.reel.png")
    img.save(folder / f"{ident}.reel.pdf", "PDF", resolution=230)
    jpg.unlink()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("folder", type=Path)
    r = sub.add_parser("run")
    r.add_argument("folder", type=Path)
    r.add_argument("engines", nargs="+")
    r.add_argument("--tessdata", default="/tessdata")
    r.add_argument("--models", default=None, help="dossier des modèles RapidOCR")
    r.add_argument("--only")
    r.add_argument("--cond", help="conditions retenues, séparées par des virgules")
    r.add_argument("--json")
    r.add_argument("-v", "--verbose", action="store_true")
    f = sub.add_parser("fetch-real")
    f.add_argument("folder", type=Path)
    a = ap.parse_args()
    if a.cmd == "gen":
        cmd_gen(a.folder)
    elif a.cmd == "run":
        cmd_run(a.folder, a.engines, a)
    else:
        cmd_fetch_real(a.folder)


if __name__ == "__main__":
    main()
