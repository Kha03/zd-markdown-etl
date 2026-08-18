import glob
import hashlib
import json
import os
import time

from google import genai
from google.genai import types
from dotenv import load_dotenv

ARTICLES_DIR = "articles"
MANIFEST_PATH = "state/manifest.json"

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

MODEL_NAME = "gemini-3.6-flash"

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

load_dotenv()


API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY was not found in .env"
    )

client = genai.Client(api_key=API_KEY)

def calculate_hash(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()

def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return {}

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest):
    os.makedirs(
        os.path.dirname(MANIFEST_PATH),
        exist_ok=True
    )

    with open(
        MANIFEST_PATH,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            manifest,
            f,
            indent=2,
            ensure_ascii=False
        )

def build_manifest_from_store(store):
    manifest = {}

    print("\nReading existing documents from Gemini Store...")

    documents = list(
        client.file_search_stores.documents.list(
            parent=store.name
        )
    )

    print(
        f"Found {len(documents)} documents in store."
    )

    for document in documents:
        display_name = document.display_name

        if not display_name:
            continue

        if not display_name.endswith(".md"):
            continue

        # article_123456.md
        article_id = (
            display_name
            .replace("article_", "")
            .replace(".md", "")
        )

        manifest[article_id] = {
            "file": display_name,
            "document_name": document.name,
        }

    return manifest


def detect_changes():
    manifest = load_manifest()

    stats = {
        "added": [],
        "updated": [],
        "skipped": [],
    }

    markdown_files = sorted(
        glob.glob(
            os.path.join(ARTICLES_DIR, "*.md")
        )
    )

    for file_path in markdown_files:

        filename = os.path.basename(file_path)

        article_id = (
            filename
           .replace("article_", "")
            .replace(".md", "")
        )

        current_hash = calculate_hash(file_path)

        old = manifest.get(article_id)

        if old is None:
            stats["added"].append({
                "article_id": article_id,
                "file_path": file_path,
                "hash": current_hash,
            })

        elif old.get("hash") == current_hash:
            stats["skipped"].append({
                "article_id": article_id,
                "file_path": file_path,
            })

        else:
            stats["updated"].append({
                "article_id": article_id,
                "file_path": file_path,
                "hash": current_hash,
                "old_document_name": old.get(
                    "document_name"
                ),
            })

    return stats


def print_change_summary(stats):

    print("\n========================================")
    print("DELTA SUMMARY")
    print("========================================")

    print(
        f"Added   : {len(stats['added'])}"
    )

    print(
        f"Updated : {len(stats['updated'])}"
    )

    print(
        f"Skipped : {len(stats['skipped'])}"
    )

    print("========================================")


def initialize_manifest_from_store(store):
    existing_manifest = load_manifest()

    if existing_manifest:
        return existing_manifest

    store_manifest = build_manifest_from_store(store)

    for article_id, item in store_manifest.items():

        local_path = os.path.join(
            ARTICLES_DIR,
            item["file"]
        )

        if os.path.exists(local_path):
            item["hash"] = calculate_hash(local_path)

    save_manifest(store_manifest)

    print(
        f"Manifest initialized with "
        f"{len(store_manifest)} documents."
    )

    return store_manifest

# ============================================================
# 2. Create a File Search Store
# ============================================================
def get_or_create_store():
    store_name = os.getenv("GEMINI_FILE_SEARCH_STORE_NAME")

    # if store_name is set in .env, try to use it
    if store_name:
        print(f"Using existing File Search Store: {store_name}")

        try:
            store = client.file_search_stores.get(
                name=store_name
            )

            print(f"Store found: {store.name}")
            return store

        except Exception as e:
            print(f"Cannot access existing store: {e}")
            raise

    # if no store_name is set, create a new store
    print("No existing File Search Store found.")
    print("Creating a new File Search Store...")

    store = client.file_search_stores.create(
        config={
            "display_name": "optibot-knowledge-base",
            "embedding_model": "models/gemini-embedding-2",
        }
    )

    print(f"Created store: {store.name}")

    print("\nAdd this to your .env:")
    print(
        f"GEMINI_FILE_SEARCH_STORE_NAME={store.name}"
    )

    return store


# ============================================================
# 3. Estimate logical chunks
# ============================================================

def estimate_chunks(file_path):
    """
    Estimate the number of logical chunks in the Markdown file.

    Gemini performs the actual chunking and embedding on the
    File Search Store side. This local calculation is only used
    for ingestion logging.
    """

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Rough token approximation:
    # 1 token ~= 4 characters for English-heavy documentation.
    estimated_tokens = max(1, len(text) // 4)

    if estimated_tokens <= CHUNK_SIZE:
        return 1

    step = CHUNK_SIZE - CHUNK_OVERLAP

    return 1 + max(
        0,
        (estimated_tokens - CHUNK_SIZE + step - 1) // step
    )


# ============================================================
# 4. Upload Markdown files directly into File Search Store
# ============================================================

def upload_article(store, file_path):
    print(f"Uploading: {file_path}")

    operation = client.file_search_stores.upload_to_file_search_store(
        file=file_path,
        file_search_store_name=store.name,
        config={
            "display_name": os.path.basename(file_path),
            "mime_type": "text/markdown",
            "chunking_config": {
                "white_space_config": {
                    "max_tokens_per_chunk": CHUNK_SIZE,
                    "max_overlap_tokens": CHUNK_OVERLAP,
                }
            },
        },
    )

    while not operation.done:
        print("  Waiting for embedding/indexing...")
        time.sleep(3)
        operation = client.operations.get(operation)

    if operation.error:
        raise RuntimeError(
            f"Failed to upload {file_path}: {operation.error}"
        )

    print(
        f"  Uploaded and indexed: "
        f"{os.path.basename(file_path)}"
    )

    return operation

def update_article(store, item):
    article_id = item["article_id"]
    file_path = item["file_path"]
    old_document_name = item.get("old_document_name")

    print(f"\nUpdating article: {article_id}")

    # Delete old document
    if old_document_name:
        print(
            f"  Deleting old document: "
            f"{old_document_name}"
        )

        client.file_search_stores.documents.delete(
            name=old_document_name,
            config={"force": True},
        )

        print("  Old document deleted.")

    # Upload new version
    operation = upload_article(
        store,
        file_path,
    )

    return operation



def sync_delta(store, stats, manifest):
    added = 0
    updated = 0

    # -----------------------------
    # Added articles
    # -----------------------------
    for item in stats["added"]:
        file_name = os.path.basename(
            item["file_path"]
        )

        upload_article(
            store,
            item["file_path"],
        )

        document = find_document_by_display_name(
            store,
            file_name,
        )

        if not document:
            raise RuntimeError(
                f"Cannot find uploaded document: {file_name}"
            )

        manifest[item["article_id"]] = {
            "file": file_name,
            "hash": item["hash"],
            "document_name": document.name,
        }

        added += 1

    # -----------------------------
    # Updated articles
    # -----------------------------
    for item in stats["updated"]:
        update_article(
            store,
            item,
        )

        file_name = os.path.basename(
            item["file_path"]
        )

        document = find_document_by_display_name(
            store,
            file_name,
        )

        if not document:
            raise RuntimeError(
                f"Cannot find updated document: {file_name}"
            )

        manifest[item["article_id"]] = {
            "file": file_name,
            "hash": item["hash"],
            "document_name": document.name,
        }

        updated += 1

    save_manifest(manifest)

    return {
        "added": added,
        "updated": updated,
        "skipped": len(stats["skipped"]),
    }

def find_document_by_display_name(store, display_name):
    documents = client.file_search_stores.documents.list(
        parent=store.name
    )

    for document in documents:
        if document.display_name == display_name:
            return document

    return None
# ============================================================
# 5. Verify documents in the store
# ============================================================

def verify_store(store):
    print("\nChecking File Search Store...")

    documents = list(
        client.file_search_stores.documents.list(
            parent=store.name
        )
    )

    print(f"Documents in store: {len(documents)}")

    active = 0
    pending = 0
    failed = 0

    for document in documents:
        state = str(document.state)

        print(
            f"- {document.display_name}: {state}"
        )

        if "ACTIVE" in state:
            active += 1
        elif "PENDING" in state:
            pending += 1
        elif "FAILED" in state:
            failed += 1

    print("\nSTORE STATUS")
    print(f"Active : {active}")
    print(f"Pending: {pending}")
    print(f"Failed : {failed}")

    if failed:
        raise RuntimeError(
            "Some documents failed during indexing."
        )

    if pending:
        print(
            "\nSome documents are still pending. "
            "Wait until they become ACTIVE."
        )


def sync_store():
    store = get_or_create_store()

    manifest = initialize_manifest_from_store(store)

    stats = detect_changes()

    print_change_summary(stats)

    result = sync_delta(
        store,
        stats,
        manifest,
    )

    print("\n========================================")
    print("SYNC RESULT")
    print("========================================")
    print(f"Added   : {result['added']}")
    print(f"Updated : {result['updated']}")
    print(f"Skipped : {result['skipped']}")
    print("========================================")

    verify_store(store)

    return result