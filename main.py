# main.py
import json
import logging
import sys
from pathlib import Path

from config import BASE_URL, PRADO_STATE_FIELD, LOG_FILE, STATE_FILE
from fetch import fetch_page, extract_prado_state
from extraction import extract_announcements_from_tree
from mongodb_utils import init_mongo, save_announcements

# Logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def load_state():
    p = Path(STATE_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}

def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state, indent=2))

def run(max_pages=None, start_page=1):
    import requests
    session = requests.Session()
    init_mongo()

    state = load_state()
    current_page = state.get("current_page", start_page)
    prado_state = state.get("prado_state", None)

    # fetch first page to get initial PRADO state
    resp, tree = fetch_page(session, BASE_URL, page_num=1, prado_state=None)
    if tree is None:
        logger.error("Impossible de récupérer la page initiale.")
        return
    #prado_state = extract_prado_state(tree) or prado_state
    prado_state = extract_prado_state(tree)

    # Estimer le nombre de pages si possible (optionnel)
    total_pages = None
    try:
        # tentative d'extraction d'un input ou d'élément indiquant nb pages — à personnaliser
        pages_raw = tree.xpath('//input[@name="totalPages"]/@value')
        if pages_raw:
            total_pages = int(pages_raw[0])
    except Exception:
        total_pages = None

    page = current_page
    pages_scraped = 0
    while True:
        if max_pages and pages_scraped >= max_pages:
            logger.info("Atteint max_pages=%s. Arrêt.", max_pages)
            break
        logger.info("Fetching page %d", page)
        resp, tree = fetch_page(session, BASE_URL, page_num=page, prado_state=prado_state)
        if tree is None:
            logger.error("Erreur récupération page %d — sauvegarde état et arrêt", page)
            save_state({"current_page": page, "prado_state": prado_state})
            break

        prado_state_new = extract_prado_state(tree)
        if prado_state_new:
            prado_state = prado_state_new

        anns = extract_announcements_from_tree(tree)
        # afficher 3 premières pour vérification
        sample = anns[:3]
        print(f"Extraites {len(anns)} annonces (exemple 3):")
        for i, s in enumerate(sample, 1):
            print(f"--- annonce {i} ---")
            for k, v in s.items():
                print(f"{k}: {v}")
            print("---------------")
        # Sauvegarder en DB
        inserted = save_announcements(anns)
        logger.info("Page %d: %d annonces extraites, %d insérées/upsert.", page, len(anns), inserted)

        # sauvegarder état
        save_state({"current_page": page + 1, "prado_state": prado_state})

        pages_scraped += 1
        # condition d'arrêt
        if total_pages and page >= total_pages:
            logger.info("Atteint total_pages=%d. Fin.", total_pages)
            break
        # si max_pages fourni, on boucle jusqu'à ce qu'il soit atteint
        page += 1

def main():
    # Ex: python3 main.py 5 -> scrape 5 pages
    max_pages = None
    if len(sys.argv) > 1:
        try:
            max_pages = int(sys.argv[1])
        except:
            pass
    run(max_pages=max_pages)

if __name__ == "__main__":
    main()
