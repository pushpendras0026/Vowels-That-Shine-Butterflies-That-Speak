"""Writes web/data/record_script.json: the exact prompts the user reads on web/record.html.
Ids match tools/fetch_ipa.py ITEMS (so the analysis pipeline is identical to the IPA-chart one) + real
diphthong glides + a few sentences.   python -m tools.make_record_script"""
from __future__ import annotations
import json
from pathlib import Path
from tools.fetch_ipa import SOUNDS as ITEMS

ROOT = Path(__file__).resolve().parents[1]
CUE = {  # what to say (plain spelling) for each id
 "i": "eeee  (as in 'see')", "ih": "ih  (as in 'sit', held)", "e": "ay WITHOUT gliding to ee (start of 'say')",
 "eh": "eh  (as in 'bed')", "ae": "aa  (as in 'cat', held)", "a": "a  (start of 'my', no glide)",
 "aa": "aah  (as in 'father')", "aw": "aw  (as in 'law')", "uh": "uh  (as in 'cup', held)",
 "o": "oh WITHOUT gliding to oo (start of 'go')", "uu": "u  (as in 'book', held)", "u": "oooo  (as in 'food')",
 "schwa": "relaxed 'uh'  (first sound of 'about')", "er": "er  (as in 'bird', tongue relaxed, no r-curl)",
 "p": "p  p  p", "b": "b  b  b", "t": "t  t  t", "d": "d  d  d", "k": "k  k  k", "g": "g  g  g",
 "m": "mmmm  (lips closed)", "n": "nnnn", "ng": "nggg  (end of 'sing', held)",
 "f": "ffff", "v": "vvvv", "th": "thhh  (as in 'thin')", "dh": "thhh voiced  (as in 'this')",
 "s": "ssss", "z": "zzzz", "sh": "shhhh", "zh": "zhhh  (middle of 'vision')", "h": "hhhh  (a breathy sigh)",
 "ch": "ch  ch  ch", "jh": "j  j  j  (as in 'jam')",
 "l": "llll  (tongue tip up, held)", "r": "rrrr  (as in 'red', held, no vowel)", "w": "wwww  (rounded lips, held 'oo-w')",
 "j": "yyyy  (as in 'yes', held)",
}
HOW = {
 "vowel": ("Hold it steady for about 2 seconds. Normal loudness, one breath.", 3),
 "nasal": ("Hold it steady for about 2 seconds.", 3), "lateral": ("Hold it steady for about 2 seconds.", 3),
 "approximant": ("Hold it steady for about 2 seconds (no vowel after it).", 3),
 "fricative": ("Hold the hiss/buzz steady for about 2 seconds.", 3),
 "plosive": ("Say ONLY the consonant 3 times with a 1-second pause between — no vowel after it (a tiny puff is fine).", 4),
 "affricate": ("Say ONLY the consonant 3 times with a 1-second pause between — no vowel after it.", 4),
}
DIPH = [("ei", "eɪ", "face", "ay-ee — slowly, 'ayyy-ee'"), ("ai", "aɪ", "price", "ah-ee — slowly, as in 'my'"),
        ("oi", "ɔɪ", "choice", "aw-ee — slowly, as in 'boy'"), ("au", "aʊ", "mouth", "ah-oo — slowly, as in 'now'"),
        ("ou", "oʊ", "goat", "oh-oo — slowly, as in 'go'")]
SENT = [("sent_butterfly", "Every vowel has a colour, and every butterfly can speak."),
        ("sent_shells", "She sells sea shells by the sea shore."),
        ("sent_birch", "The birch canoe slid on the smooth planks."),
        ("sent_rainbow", "When the sunlight strikes raindrops in the air, they act as a prism and form a rainbow.")]

def main():
    out = []
    for (sid, ipa, name, example, kind, cls, voiced, _files) in ITEMS:
        how, sec = HOW[cls]
        out.append(dict(id=sid, ipa=ipa, group=cls, example=example, name=name, say=CUE[sid], how=how, seconds=sec))
    for sid, ipa, ex, cue in DIPH:
        out.append(dict(id=sid, ipa=ipa, group="diphthong", example=ex, name="diphthong", say=cue,
                        how="One slow glide, about 1 second, start vowel to end vowel. Say it 2 times with a pause.",
                        seconds=4))
    for sid, txt in SENT:
        out.append(dict(id=sid, ipa="", group="sentence", example="", name="sentence", say=txt,
                        how="Read it naturally, at your normal speed.", seconds=6))
    p = ROOT / "web" / "data" / "record_script.json"
    p.write_text(json.dumps(dict(prompts=out), ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(out), "prompts ->", p.relative_to(ROOT))

if __name__ == "__main__":
    main()
