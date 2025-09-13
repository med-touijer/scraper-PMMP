# mongodb_utils.py
import logging
from pymongo import MongoClient, UpdateOne
from config import MONGO_URI, DB_NAME, COLLECTION_NAME

logger = logging.getLogger(__name__)

client = None
db = None
collection = None

def init_mongo():
    global client, db, collection
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    # Index pour éviter doublons (sur lienDeConsultation si disponible)
    collection.create_index("lienDeConsultation", unique=True, sparse=True)
    collection.create_index([("reference", 1), ("datePublication", 1)])

def save_announcements(announcements, upsert=True):
    """
    Insère ou met à jour les annonces. Utilise upsert sur 'lienDeConsultation' si présent,
    sinon insère normalement.
    """
    if not announcements:
        return 0
    ops = []
    for a in announcements:
        # Normaliser (convertir datetime en ce que pymongo accepte est automatique)
        query = {}
        if a.get("lienDeConsultation") and a["lienDeConsultation"] != "N/A":
            query = {"lienDeConsultation": a["lienDeConsultation"]}
        elif a.get("reference") and a["reference"] != "N/A":
            query = {"reference": a["reference"], "datePublication": a.get("datePublication")}
        else:
            # fallback: insert direct
            ops.append(a)
            continue

        # Prepare UpdateOne
        ops.append(UpdateOne(query, {"$set": a}, upsert=True))

    # Séparer inserts purs de bulk ops
    bulk_ops = [op for op in ops if hasattr(op, "upsert") or isinstance(op, UpdateOne)]
    plain_inserts = [op for op in ops if not hasattr(op, "upsert") and not isinstance(op, UpdateOne)]
    inserted = 0
    if bulk_ops:
        result = collection.bulk_write(bulk_ops, ordered=False)
        inserted += getattr(result, "upserted_count", 0) + getattr(result, "inserted_count", 0)
    if plain_inserts:
        res = collection.insert_many(plain_inserts)
        inserted += len(res.inserted_ids)
    return inserted
