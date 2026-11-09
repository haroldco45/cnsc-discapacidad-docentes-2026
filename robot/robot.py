"""Robot de Vibras Positivas HM.
- Noticias reales del concurso docente / vacantes con discapacidad (Google News RSS) -> noticias.json
- Fotos reales con licencia libre de Wikimedia Commons -> img/foto-N.jpg + img/creditos.json
- Imagen de vista previa (og-image.jpg) con foto real
Corre en GitHub Actions. Solo escribe archivos si algo cambió.
"""
import json, os, re, io, html, hashlib, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COT = timezone(timedelta(hours=-5))
UA = "VibrasPositivasHM-Robot/1.0 (https://cnsc-discapacidad-docentes-2026.netlify.app)"

def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

# ---------------- Noticias ----------------
QUERIES = [
    'CNSC docentes discapacidad inscripciones',
    '"concurso docente" discapacidad CNSC',
    'CNSC "11673"',
    '"concurso docente" CNSC 2026',
]
KEYS = re.compile(r'(docent|magisterio|cnsc|discapacidad|concurso)', re.I)

def noticias():
    items, seen = [], set()
    for q in QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": q + " when:60d", "hl": "es-419", "gl": "CO", "ceid": "CO:es-419"})
        try:
            root = ET.fromstring(get(url))
        except Exception as e:
            print("RSS falló:", q, e); continue
        for it in root.iter("item"):
            title = html.unescape(it.findtext("title") or "").strip()
            src_el = it.find("source")
            source = (src_el.text or "").strip() if src_el is not None else ""
            if source and title.endswith(" - " + source):
                title = title[: -len(source) - 3].strip()
            if not KEYS.search(title):
                continue
            key = re.sub(r'\W+', '', title.lower())[:80]
            if key in seen:
                continue
            seen.add(key)
            try:
                dt = parsedate_to_datetime(it.findtext("pubDate")).astimezone(COT)
            except Exception:
                continue
            items.append({"titulo": title, "fuente": source, "link": it.findtext("link"),
                          "fecha": dt.isoformat()})
    items.sort(key=lambda x: x["fecha"], reverse=True)
    return items[:30]

# ---------------- Fotos (Wikimedia Commons, licencias libres) ----------------
PHOTO_QUERIES = [
    'classroom Colombia teacher', 'escuela Colombia aula', 'maestra Colombia estudiantes',
    'docente aula Colombia', 'school Colombia students classroom', 'wheelchair classroom teacher',
    'sign language class', 'escuela rural Colombia',
]
OK_LIC = re.compile(r'^(cc0|cc[- ]by(-sa)?[- ]?\d|public domain|pd)', re.I)

def strip_tags(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s or '')).strip()

def commons_candidates():
    out, seen = [], set()
    for q in PHOTO_QUERIES:
        p = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
             "gsrsearch": q + " filetype:bitmap", "gsrlimit": 15, "prop": "imageinfo",
             "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600}
        try:
            data = json.loads(get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p)))
        except Exception as e:
            print("Commons falló:", q, e); continue
        for pg in (data.get("query", {}).get("pages", {}) or {}).values():
            ii = (pg.get("imageinfo") or [{}])[0]
            if ii.get("mime") != "image/jpeg": continue
            if ii.get("width", 0) < 1200 or ii.get("width", 0) < ii.get("height", 1): continue
            md = ii.get("extmetadata", {})
            lic = strip_tags(md.get("LicenseShortName", {}).get("value"))
            if not OK_LIC.match(lic): continue
            if pg["title"] in seen: continue
            seen.add(pg["title"])
            out.append({"titulo": pg["title"].replace("File:", ""), "thumb": ii.get("thumburl"),
                        "pagina": ii.get("descriptionurl"),
                        "autor": strip_tags(md.get("Artist", {}).get("value"))[:120] or "Wikimedia Commons",
                        "licencia": lic, "query": q})
    return out

def fotos():
    cred_path = os.path.join(ROOT, "img", "creditos.json")
    fijas = os.path.join(ROOT, "img", "fijas.json")  # lista curada a mano (opcional)
    if os.path.exists(cred_path):
        cred = json.load(open(cred_path, encoding="utf-8"))
        if cred and all(os.path.exists(os.path.join(ROOT, "img", c["archivo"])) for c in cred):
            return cred, False  # ya están: no se tocan
    cands = commons_candidates()
    if os.path.exists(fijas):
        wanted = json.load(open(fijas, encoding="utf-8"))
        cands = [c for w in wanted for c in cands if c["titulo"] == w] or cands
    from PIL import Image
    cred = []
    for c in cands:
        if len(cred) >= 6: break
        try:
            im = Image.open(io.BytesIO(get(c["thumb"]))).convert("RGB")
        except Exception as e:
            print("No bajó:", c["titulo"], e); continue
        im.thumbnail((1600, 1600))
        name = f"foto-{len(cred)+1}.jpg"
        im.save(os.path.join(ROOT, "img", name), quality=82, optimize=True)
        c["archivo"] = name
        cred.append(c)
    os.makedirs(os.path.join(ROOT, "img"), exist_ok=True)
    json.dump(cred, open(cred_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return cred, True

def og(cred):
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1200, 630
    base = Image.new("RGB", (W, H), (15, 61, 62))
    if cred:
        ph = Image.open(os.path.join(ROOT, "img", cred[0]["archivo"])).convert("RGB")
        r = max(W / ph.width, H / ph.height)
        ph = ph.resize((int(ph.width * r) + 1, int(ph.height * r) + 1))
        ph = ph.crop(((ph.width - W) // 2, (ph.height - H) // 2, (ph.width - W) // 2 + W, (ph.height - H) // 2 + H))
        base.paste(ph)
    shade = Image.new("RGBA", (W, H))
    sd = ImageDraw.Draw(shade)
    for x in range(W):
        a = int(235 * max(0, 1 - x / (W * 0.85)) + 40)
        sd.line([(x, 0), (x, H)], fill=(11, 43, 44, min(255, a)))
    base = Image.alpha_composite(base.convert("RGBA"), shade).convert("RGB")
    d = ImageDraw.Draw(base)
    fb = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    fr = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    F = lambda p, s: ImageFont.truetype(p, s)
    amber, white = (227, 165, 42), (255, 255, 255)
    d.rounded_rectangle([56, 50, 590, 92], 6, fill=amber)
    d.text((72, 58), "RESOLUCIÓN CNSC 11673 · 6 NOV 2026", font=F(fb, 23), fill=(15, 61, 62))
    d.text((56, 120), "2.255", font=F(fb, 150), fill=amber)
    d.text((58, 300), "plazas de profe reservadas", font=F(fb, 50), fill=white)
    d.text((58, 360), "para personas con discapacidad", font=F(fb, 50), fill=white)
    d.text((58, 448), "Inscripción gratis: 23 nov 2026 – 15 ene 2027", font=F(fr, 31), fill=(220, 236, 228))
    d.text((58, 530), "cnsc-discapacidad-docentes-2026.netlify.app", font=F(fb, 24), fill=amber)
    for i, col in enumerate([(127, 200, 169), amber, (214, 90, 63)]):
        d.rectangle([i * W // 3, H - 12, (i + 1) * W // 3, H], fill=col)
    base.save(os.path.join(ROOT, "og-image.jpg"), quality=88)

def main():
    path = os.path.join(ROOT, "noticias.json")
    old = {}
    if os.path.exists(path):
        try: old = json.load(open(path, encoding="utf-8"))
        except Exception: old = {}
    items = noticias()
    if not items and old.get("noticias"):
        items = old["noticias"]  # si Google falla, no borramos lo que había
    h = hashlib.sha1(json.dumps(items, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if h != old.get("hash"):
        json.dump({"actualizado": datetime.now(COT).isoformat(timespec="minutes"), "hash": h,
                   "noticias": items}, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("noticias.json actualizado:", len(items))
    else:
        print("Noticias sin cambios")
    cred, nuevas = fotos()
    og(cred)  # determinista: si nada cambió, git no ve diferencia
    print("Fotos:", [c["archivo"] for c in cred])

if __name__ == "__main__":
    main()
