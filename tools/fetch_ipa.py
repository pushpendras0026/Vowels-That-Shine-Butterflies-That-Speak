"""Download the standard IPA-chart recordings from Wikimedia Commons (the ones used on Wikipedia's IPA pages).

    . .\\tools\\env.ps1; python -m tools.fetch_ipa          # skips files already in data/ipa/raw/

Writes data/ipa/raw/<id>.ogg plus data/ipa/ATTRIBUTION.json and data/ipa/ATTRIBUTION.md (title, URL, author,
licence per file, from the Commons API extmetadata). Files whose licence is not CC / public domain are skipped.
Only network access: commons.wikimedia.org API + upload.wikimedia.org (generic educational User-Agent).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ipa"
RAW = OUT / "raw"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "DA321-course-project/1.0 (educational)"}

# id, IPA, name, example word, kind, class, voiced, [Commons titles to try, first that exists wins]
SOUNDS = [
    # ---- monophthong vowels (English-relevant)
    ("i", "i", "close front unrounded vowel", "fleece", "vowel", "vowel", True, ["Close front unrounded vowel.ogg"]),
    ("ih", "ɪ", "near-close near-front unrounded vowel", "kit", "vowel", "vowel", True,
     ["Near-close near-front unrounded vowel.ogg"]),
    ("e", "e", "close-mid front unrounded vowel", "face (start)", "vowel", "vowel", True,
     ["Close-mid front unrounded vowel.ogg"]),
    ("eh", "ɛ", "open-mid front unrounded vowel", "dress", "vowel", "vowel", True,
     ["Open-mid front unrounded vowel.ogg"]),
    ("ae", "æ", "near-open front unrounded vowel", "trap", "vowel", "vowel", True,
     ["Near-open front unrounded vowel.ogg"]),
    ("a", "a", "open front unrounded vowel", "price (start)", "vowel", "vowel", True, ["Open front unrounded vowel.ogg"]),
    ("aa", "ɑ", "open back unrounded vowel", "palm", "vowel", "vowel", True, ["Open back unrounded vowel.ogg"]),
    ("aw", "ɔ", "open-mid back rounded vowel", "thought", "vowel", "vowel", True, ["Open-mid back rounded vowel.ogg"]),
    ("uh", "ʌ", "open-mid back unrounded vowel", "strut", "vowel", "vowel", True, ["Open-mid back unrounded vowel.ogg"]),
    ("o", "o", "close-mid back rounded vowel", "goat (start)", "vowel", "vowel", True,
     ["Close-mid back rounded vowel.ogg"]),
    ("uu", "ʊ", "near-close near-back rounded vowel", "foot", "vowel", "vowel", True,
     ["Near-close near-back rounded vowel.ogg"]),
    ("u", "u", "close back rounded vowel", "goose", "vowel", "vowel", True, ["Close back rounded vowel.ogg"]),
    ("schwa", "ə", "mid central vowel", "about", "vowel", "vowel", True, ["Mid-central vowel.ogg", "Mid central vowel.ogg"]),
    ("er", "ɜ", "open-mid central unrounded vowel", "nurse", "vowel", "vowel", True,
     ["Open-mid central unrounded vowel.ogg"]),
    # ---- plosives
    ("p", "p", "voiceless bilabial plosive", "pin", "consonant", "plosive", False, ["Voiceless bilabial plosive.ogg"]),
    ("b", "b", "voiced bilabial plosive", "bin", "consonant", "plosive", True, ["Voiced bilabial plosive.ogg"]),
    ("t", "t", "voiceless alveolar plosive", "tin", "consonant", "plosive", False, ["Voiceless alveolar plosive.ogg"]),
    ("d", "d", "voiced alveolar plosive", "din", "consonant", "plosive", True, ["Voiced alveolar plosive.ogg"]),
    ("k", "k", "voiceless velar plosive", "kin", "consonant", "plosive", False, ["Voiceless velar plosive.ogg"]),
    ("g", "ɡ", "voiced velar plosive", "go", "consonant", "plosive", True, ["Voiced velar plosive.ogg"]),
    # ---- nasals
    ("m", "m", "bilabial nasal", "man", "consonant", "nasal", True, ["Bilabial nasal.ogg"]),
    ("n", "n", "alveolar nasal", "no", "consonant", "nasal", True, ["Alveolar nasal.ogg"]),
    ("ng", "ŋ", "velar nasal", "sing", "consonant", "nasal", True, ["Velar nasal.ogg"]),
    # ---- fricatives
    ("f", "f", "voiceless labiodental fricative", "fan", "consonant", "fricative", False,
     ["Voiceless labiodental fricative.ogg"]),
    ("v", "v", "voiced labiodental fricative", "van", "consonant", "fricative", True,
     ["Voiced labiodental fricative.ogg"]),
    ("th", "θ", "voiceless dental fricative", "thin", "consonant", "fricative", False,
     ["Voiceless dental fricative.ogg"]),
    ("dh", "ð", "voiced dental fricative", "this", "consonant", "fricative", True, ["Voiced dental fricative.ogg"]),
    ("s", "s", "voiceless alveolar sibilant", "sip", "consonant", "fricative", False,
     ["Voiceless alveolar sibilant.ogg"]),
    ("z", "z", "voiced alveolar sibilant", "zip", "consonant", "fricative", True, ["Voiced alveolar sibilant.ogg"]),
    ("sh", "ʃ", "voiceless postalveolar fricative", "ship", "consonant", "fricative", False,
     ["Voiceless palato-alveolar sibilant.ogg", "Voiceless postalveolar fricative.ogg",
      "Voiceless palato-alveolar fricative.ogg"]),
    ("zh", "ʒ", "voiced postalveolar fricative", "vision", "consonant", "fricative", True,
     ["Voiced palato-alveolar sibilant.ogg", "Voiced postalveolar fricative.ogg",
      "Voiced palato-alveolar fricative.ogg"]),
    ("h", "h", "voiceless glottal fricative", "hat", "consonant", "fricative", False,
     ["Voiceless glottal fricative.ogg"]),
    # ---- affricates (added 2026-11-23)
    ("ch", "tʃ", "voiceless postalveolar affricate", "chin", "consonant", "affricate", False,
     ["Voiceless palato-alveolar affricate.ogg", "Voiceless postalveolar affricate.ogg"]),
    ("jh", "dʒ", "voiced postalveolar affricate", "jam", "consonant", "affricate", True,
     ["Voiced palato-alveolar affricate.ogg", "Voiced postalveolar affricate.ogg"]),
    # ---- approximants
    ("l", "l", "alveolar lateral approximant", "leaf", "consonant", "lateral", True,
     ["Alveolar lateral approximant.ogg"]),
    ("r", "ɹ", "alveolar approximant", "red", "consonant", "approximant", True, ["Alveolar approximant.ogg"]),
    ("w", "w", "labial-velar approximant", "wet", "consonant", "approximant", True,
     ["Voiced labio-velar approximant.ogg", "Labial-velar approximant.ogg", "Voiced labial-velar approximant.ogg"]),
    ("j", "j", "palatal approximant", "yes", "consonant", "approximant", True, ["Palatal approximant.ogg"]),
]

FREE = re.compile(r"(^|\b)(cc[- ]?by|cc[- ]?zero|cc0|public domain|pd\b|pd-)", re.I)


def strip_html(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def sha1(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def query(titles):
    r = requests.get(API, params=dict(action="query", format="json", prop="imageinfo", redirects=1,
                                      iiprop="url|extmetadata|mime|size|sha1",
                                      titles="|".join("File:" + t for t in titles)), headers=UA, timeout=30)
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    out = {}
    for p in pages.values():
        if "imageinfo" in p:
            out[p["title"].removeprefix("File:")] = p["imageinfo"][0]
    return out


def download(url, tries=6):
    """Polite download: 3 s between files, back off on HTTP 429 (honours Retry-After)."""
    url = url.split("?")[0]
    for k in range(tries):
        time.sleep(3.0)
        r = requests.get(url, headers=UA, timeout=60)
        if r.status_code == 429 and k < tries - 1:
            wait = float(r.headers.get("Retry-After", "0") or 0) or 15.0 * (k + 1)
            print(f"    429, waiting {wait:.0f} s")
            time.sleep(min(wait, 120.0))
            continue
        r.raise_for_status()
        return r.content
    raise RuntimeError("too many retries")


def main(argv):
    RAW.mkdir(parents=True, exist_ok=True)
    all_titles = sorted({t for s in SOUNDS for t in s[7]})
    info = {}
    for i in range(0, len(all_titles), 40):
        info.update(query(all_titles[i:i + 40]))
    attrib, skipped = [], []
    for sid, ipa, name, ex, kind, cls, voiced, titles in SOUNDS:
        hit = next((t for t in titles if t in info), None)
        if hit is None:
            skipped.append(dict(id=sid, reason=f"not found on Commons: {titles}"))
            print(f"  skip {sid}: not found")
            continue
        ii = info[hit]
        md = ii.get("extmetadata", {})
        lic = strip_html(md.get("LicenseShortName", {}).get("value", ""))
        lic_url = md.get("LicenseUrl", {}).get("value", "")
        author = strip_html(md.get("Artist", {}).get("value", "")) or "unknown"
        if not FREE.search(lic):
            skipped.append(dict(id=sid, title=hit, reason=f"licence not CC/PD: {lic!r}"))
            print(f"  skip {sid}: licence {lic!r}")
            continue
        ext = Path(ii["url"].split("?")[0]).suffix.lower() or ".ogg"
        dst = RAW / f"{sid}{ext}"
        want = ii.get("sha1", "").lower()
        if not (dst.exists() and sha1(dst) == want):
            src = next((p for p in RAW.iterdir() if p.is_file() and p != dst and sha1(p) == want), None)
            try:
                if src is not None:                 # already downloaded under another name: reuse (hash-verified)
                    dst.write_bytes(src.read_bytes())
                else:
                    data = download(ii["url"])
                    if want and hashlib.sha1(data).hexdigest() != want:
                        raise ValueError("sha1 mismatch")
                    dst.write_bytes(data)
            except Exception as e:  # noqa: BLE001
                skipped.append(dict(id=sid, title=hit, reason=f"download failed: {e}"))
                print(f"  skip {sid}: download failed {e}")
                continue
        attrib.append(dict(id=sid, ipa=ipa, name=name, example=ex, kind=kind, cls=cls, voiced=voiced,
                           title="File:" + hit, file=f"data/ipa/raw/{dst.name}", url=ii["url"],
                           page=ii.get("descriptionurl", ""), author=author, license=lic, license_url=lic_url,
                           mime=ii.get("mime", ""), sha1=want, bytes=dst.stat().st_size))
        print(f"  ok   {sid:6s} {lic:16s} {hit}")
    keep = {Path(a["file"]).name for a in attrib}
    for p in RAW.iterdir():                          # leftovers (e.g. partial/renamed files)
        if p.is_file() and p.name not in keep and len(skipped) == 0:
            p.unlink()
    (OUT / "ATTRIBUTION.json").write_text(json.dumps(dict(
        source="Wikimedia Commons IPA chart recordings (as used on Wikipedia's IPA pages)",
        fetched_with="python -m tools.fetch_ipa (Commons API prop=imageinfo, iiprop=url|extmetadata)",
        items=attrib, skipped=skipped), indent=1, ensure_ascii=False), encoding="utf-8")
    lines = ["# IPA recordings — attribution", "",
             "Audio recordings from Wikimedia Commons (the IPA-chart files used on Wikipedia's IPA pages).",
             "Downloaded by `python -m tools.fetch_ipa`; only CC / public-domain files are kept. "
             "Derived 16 kHz WAVs are in `web/audio/ipa/` (resampled and unchanged otherwise).", "",
             "| id | IPA | sound | file | author | licence |", "|---|---|---|---|---|---|"]
    for a in attrib:
        lic = f"[{a['license']}]({a['license_url']})" if a["license_url"] else a["license"]
        lines.append(f"| {a['id']} | {a['ipa']} | {a['name']} | [{a['title']}]({a['page']}) | "
                     f"{a['author'].replace('|', '/')} | {lic} |")
    if skipped:
        lines += ["", "Skipped:", ""] + [f"- {s['id']}: {s['reason']}" for s in skipped]
    (OUT / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(attrib)} files kept, {len(skipped)} skipped -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
