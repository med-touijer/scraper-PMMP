# fetch.py — remplacer les fonctions extract_prado_state et fetch_page par ceci
import time
import logging
import requests
from lxml import html

from config import BASE_URL, HEADERS, REQUEST_TIMEOUT, DELAY_BETWEEN_REQUESTS, PRADO_STATE_FIELD, PAGER_TARGET, NUM_PAGE_FIELD, PRADO_POSTBACK_TARGET

logger = logging.getLogger(__name__)

def extract_prado_state(tree):
    """
    Cherche la valeur PRADO_PAGESTATE ou PRADO_PAGE_STATE (compatibilité).
    """
    for name in ("PRADO_PAGESTATE", "PRADO_PAGE_STATE"):
        try:
            val = tree.xpath(f'//input[@name="{name}"]/@value')
            if val:
                return val[0]
        except Exception:
            continue
    return None

def fetch_page(session: requests.Session, url: str, page_num: int = 1, prado_state: str = None, max_retries=3):
    """
    Récupère la page. Si page_num > 1, simule le postback PRADO (pagination).
    """
    for attempt in range(1, max_retries + 1):
        try:
            if page_num == 1:
                resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            else:
                # Corps POST similaire au formulaire PRADO observé
                data = {
                    "PRADO_PAGESTATE": prado_state or "",
                    "PRADO_POSTBACK_TARGET": PAGER_TARGET,
                    "PRADO_POSTBACK_PARAMETER": "",
                    NUM_PAGE_FIELD: str(page_num),
                    # certains formulaires envoient aussi le champ DefaultButtonTop, etc. si besoin, ajoute-les
                }
                resp = session.post(url, headers=HEADERS, data=data, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            tree = html.fromstring(resp.content)
            time.sleep(DELAY_BETWEEN_REQUESTS)
            return resp, tree
        except requests.RequestException as e:
            logger.warning("Attempt %d: erreur fetch page %s (page %d): %s", attempt, url, page_num, e)
            time.sleep(2 * attempt)
    logger.error("Échec après %d tentatives pour la page %d", max_retries, page_num)
    return None, None

