# extraction.py
"""
Robust extraction for marchespublics.gov.ma result table.

Provides:
- extract_announcement(row) -> dict
- extract_announcements_from_tree(tree) -> list[dict]

Usage: keep this file in your project and `main.py` can import
`extract_announcements_from_tree` as before.
You can also run:
    python3 extraction.py simple_body.html
to test locally.
"""

import re
from datetime import datetime
from lxml import html
from pathlib import Path

BASE = "https://www.marchespublics.gov.ma"

def parse_date(date_str):
    """Find DD/MM/YYYY (optionally HH:MM) and return datetime or None."""
    if not date_str:
        return None
    s = date_str.strip()
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})(?:\s+(\d{1,2}:\d{2}))?", s)
    if not m:
        return None
    date_part = m.group(1)
    time_part = m.group(2)
    if time_part:
        fmt = "%d/%m/%Y %H:%M"
        as_str = f"{date_part} {time_part}"
    else:
        fmt = "%d/%m/%Y"
        as_str = date_part
    try:
        return datetime.strptime(as_str, fmt)
    except Exception:
        return None

def normalize_popup_link(href):
    """Convert javascript popUp(...) into an absolute URL."""
    if not href:
        return "N/A"
    href = href.strip()
    if href.startswith("http"):
        return href
    m = re.search(r"popUp\(\s*'([^']+)'", href)
    if m:
        inner = m.group(1)
        if inner.startswith("/"):
            return BASE + inner
        if inner.startswith("index.php"):
            return BASE + "/" + inner
        if inner.startswith("?"):
            return BASE + "/index.php" + inner
        if inner.startswith("page="):
            return BASE + "/index.php?" + inner
        return BASE + "/index.php?" + inner
    if href.startswith("index.php"):
        return BASE + "/" + href
    if href.startswith("?"):
        return BASE + "/index.php" + href
    return href

def uniq_preserve(seq):
    seen = set()
    out = []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def extract_announcement(row):
    """
    Extract single announcement from an lxml <tr> row.
    Returns a dict following your schema (with Python datetime for dates).
    """
    ann = {}

    # Cells
    cell_ref = row.xpath('.//td[@headers="cons_ref"]')
    cell_intitule = row.xpath('.//td[@headers="cons_intitule"]')
    cell_lieu = row.xpath('.//td[@headers="cons_lieuExe"]')
    cell_dateend = row.xpath('.//td[@headers="cons_dateEnd"]')

    # PROCEDURE
    ann["procedure"] = "N/A"
    if cell_ref:
        li = cell_ref[0].xpath('.//div[contains(@class,"line-info-bulle")]')
        if li:
            txt = li[0].text_content().strip()
            if txt:
                ann["procedure"] = txt.split()[0].strip()
        if ann["procedure"] == "N/A":
            # fallback: find uppercase code
            all_txt = cell_ref[0].text_content()
            m = re.search(r'\b([A-Z]{2,4})\b', all_txt)
            if m:
                ann["procedure"] = m.group(1)

    # CATEGORIE
    ann["categorie"] = "N/A"
    if cell_ref:
        cat = cell_ref[0].xpath('.//div[contains(@id,"panelBlocCategorie")]')
        if cat:
            ann["categorie"] = cat[0].text_content().strip()

    # DATE PUBLICATION
    ann["datePublication"] = None
    if cell_ref:
        text_ref = cell_ref[0].text_content()
        ann["datePublication"] = parse_date(text_ref)

    # REFERENCE
    ann["reference"] = "N/A"
    if cell_intitule:
        ref = cell_intitule[0].xpath('.//span[@class="ref"]/text()')
        if ref:
            ann["reference"] = ref[0].strip()

    # OBJET
    ann["objet"] = "N/A"
    if cell_intitule:
        obj_el = cell_intitule[0].xpath('.//div[contains(@id,"panelBlocObjet")]')
        if obj_el:
            txt = obj_el[0].text_content().strip()
            # remove "Objet :" label if present
            txt = re.sub(r'^\s*Objet\s*:?\s*', '', txt, flags=re.IGNORECASE).strip()
            if txt:
                ann["objet"] = " ".join(txt.split())
        else:
            # fallback: find a <strong> that contains "Objet" and take its parent text_content
            strongs = cell_intitule[0].xpath('.//strong[contains(translate(.,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"objet")]')
            if strongs:
                parent = strongs[0].getparent()
                if parent is not None:
                    txt = parent.text_content()
                    txt = re.sub(r'^\s*Objet\s*:?\s*', '', txt, flags=re.IGNORECASE).strip()
                    if txt:
                        ann["objet"] = " ".join(txt.split())

    # ACHETEUR PUBLIC
    ann["acheteurPublic"] = "N/A"
    if cell_intitule:
        achet = cell_intitule[0].xpath('.//div[contains(@id,"panelBlocDenomination")]')
        if achet:
            txt = achet[0].text_content().strip()
            txt = re.sub(r'^\s*Acheteur\s*public\s*:?\s*', '', txt, flags=re.IGNORECASE).strip()
            if txt:
                ann["acheteurPublic"] = " ".join(txt.split())
        else:
            sp = cell_intitule[0].xpath('.//strong[contains(translate(.,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"acheteur")]')
            if sp:
                p = sp[0].getparent()
                if p is not None:
                    txt = p.text_content()
                    txt = re.sub(r'^\s*Acheteur\s*public\s*:?\s*', '', txt, flags=re.IGNORECASE).strip()
                    if txt:
                        ann["acheteurPublic"] = " ".join(txt.split())

    # LOTS
    ann["lots"] = "-"
    if cell_lieu:
        s = cell_lieu[0].xpath('.//span[1]/text()')
        if s:
            candidate = s[0].strip()
            ann["lots"] = candidate if candidate else "-"

    # LIEU D'EXECUTION: prefer direct child text of the panelBlocLieuxExec (avoid nested info-bubble duplication)
    ann["lieuExecution"] = "N/A"
    if cell_lieu:
        panel = cell_lieu[0].xpath('.//div[contains(@id,"panelBlocLieuxExec")]')
        if panel:
            # direct text nodes under panel (not recursing into nested info-bulle)
            direct_texts = [t.strip() for t in panel[0].xpath('./text()') if t.strip()]
            # also consider text from immediate child <br/> separated content by joining direct_texts
            if direct_texts:
                ann["lieuExecution"] = ", ".join(direct_texts)
            else:
                # fallback: sometimes text is nested but not in direct text nodes -> take panel text_content but remove info-bubble repeated text
                all_txt = panel[0].text_content().strip()
                # remove '...' markers and excessive whitespace
                cleaned = " ".join([ln.strip() for ln in re.split(r'[\r\n]+', all_txt) if ln.strip() and not ln.strip().startswith("...")])
                if cleaned:
                    ann["lieuExecution"] = cleaned

    # DATE LIMITE
    ann["dateLimite"] = None
    if cell_dateend:
        txt = cell_dateend[0].text_content()
        ann["dateLimite"] = parse_date(txt)

    # PIECES JOINTES
    ann["piecesJointes"] = []
    hrefs = row.xpath('.//a/@href')
    for h in hrefs:
        if h and ('.pdf' in h.lower() or 'download' in h.lower() or 'pieces' in h.lower()):
            if h.startswith('/'):
                ann["piecesJointes"].append(BASE + h)
            elif h.startswith('http'):
                ann["piecesJointes"].append(h)
            else:
                ann["piecesJointes"].append(BASE + '/' + h.lstrip('/'))

    # LIEN DE CONSULTATION
    link = ""
    if cell_lieu:
        link_candidates = cell_lieu[0].xpath('.//a[contains(@href,"popUp")]/@href')
        if link_candidates:
            link = link_candidates[0]
    if not link:
        alt = row.xpath('.//a[contains(@href,"refConsultation")]/@href')
        if alt:
            link = alt[0]
    ann["lienDeConsultation"] = normalize_popup_link(link)

    # Ensure keys exist and default values
    defaults = {
        "procedure": "N/A",
        "categorie": "N/A",
        "datePublication": None,
        "reference": "N/A",
        "objet": "N/A",
        "acheteurPublic": "N/A",
        "lots": "-",
        "lieuExecution": "N/A",
        "dateLimite": None,
        "piecesJointes": [],
        "lienDeConsultation": "N/A",
    }
    for k, v in defaults.items():
        if k not in ann or ann[k] is None:
            ann[k] = v

    return ann

def extract_announcements_from_tree(tree):
    """
    Given an lxml tree, return list of announcement dicts.
    """
    rows = tree.xpath('//table[contains(@class,"table-results")]//tr[td]')
    announcements = []
    for row in rows:
        try:
            ann = extract_announcement(row)
            # Heuristic: include if at least reference or objet present or hidden refCons input exists
            if (ann.get("reference") and ann["reference"] != "N/A") or (ann.get("objet") and ann["objet"] != "N/A"):
                announcements.append(ann)
            else:
                ref_hidden = row.xpath('.//input[contains(@id,"refCons")]/@value')
                if ref_hidden:
                    announcements.append(ann)
        except Exception as e:
            # don't crash for one bad row
            print("Warning: failed to extract row:", e)
            continue
    return announcements

if __name__ == "__main__":
    # quick local test
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python extraction.py simple_body.html")
        sys.exit(0)
    path = Path(sys.argv[1])
    tree = html.fromstring(path.read_bytes())
    anns = extract_announcements_from_tree(tree)
    def conv(o):
        if isinstance(o, datetime):
            return o.isoformat()
        return o
    print(json.dumps(anns, ensure_ascii=False, indent=2, default=conv))

