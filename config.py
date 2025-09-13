# config.py
# Configuration centralisée pour le scraper

BASE_URL = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&searchAnnCons&keyWord="

# Sélecteurs (à ajuster si simple_body.html diffère)
RESULT_TABLE_SELECTOR = "//table[@class='table-results']//tr[td]"  # toutes les lignes contenant td
#PRADO_STATE_FIELD = "PRADO_PAGE_STATE"
PRADO_STATE_FIELD = "PRADO_PAGESTATE"

# Champs requis pour la pagination PRADO (peuvent devoir être adaptés)
PAGER_TARGET = "ctl0$CONTENU_PAGE$resultSearch$PagerTop$ctl2"
NUM_PAGE_FIELD = "ctl0$CONTENU_PAGE$resultSearch$numPageTop"
PRADO_POSTBACK_TARGET = "PRADO_POSTBACK_TARGET"

# MongoDB
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "marches_publics"
COLLECTION_NAME = "annonces"

# Requêtes / delays / headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Scraper pour analyse des marchés publics)"
}
REQUEST_TIMEOUT = 15  # secondes
DELAY_BETWEEN_REQUESTS = 2  # secondes

# Fichiers utilitaires
LOG_FILE = "scraper.log"
STATE_FILE = "state.json"
SIMPLE_BODY_TEST = "simple_body.html"  # fichier d'exemple fourni
