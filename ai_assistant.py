import glob
import os
import time
from urllib import response

from dotenv import load_dotenv
from google import genai
from google.genai import types


# ============================================================
# 1. Configuration
# ============================================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY was not found in .env"
    )

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-3.6-flash"

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

ARTICLES_DIR = "articles"

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50


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

def upload_articles(store):
    markdown_files = sorted(
        glob.glob(os.path.join(ARTICLES_DIR, "*.md"))
    )

    if not markdown_files:
        raise FileNotFoundError(
            "No Markdown files found in articles/"
        )

    uploaded_count = 0
    estimated_chunk_count = 0

    print(f"\nFound {len(markdown_files)} Markdown files.")

    for file_path in markdown_files:

        print(f"\nUploading: {file_path}")

        estimated_chunks = estimate_chunks(file_path)

        estimated_chunk_count += estimated_chunks

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

        # Wait until indexing / embedding is finished.
        while not operation.done:
            print("  Waiting for embedding/indexing...")
            time.sleep(3)
            operation = client.operations.get(operation)

        if operation.error:
            raise RuntimeError(
                f"Failed to upload {file_path}: {operation.error}"
            )

        uploaded_count += 1

        print(
            f"  Uploaded and indexed: "
            f"{os.path.basename(file_path)}"
        )

    print("\n========================================")
    print("INGESTION SUMMARY")
    print("========================================")
    print(f"Files uploaded: {uploaded_count}")
    print(
        f"Estimated logical chunks: "
        f"{estimated_chunk_count}"
    )
    print(
        f"Chunking: {CHUNK_SIZE} tokens, "
        f"{CHUNK_OVERLAP} overlap"
    )
    print("========================================")

    return uploaded_count, estimated_chunk_count


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


# ============================================================
# 6. Ask Gemini using File Search
# ============================================================

def sanity_check(store):
    question = "How do I add a YouTube video?"

    print("\n========================================")
    print("SANITY CHECK")
    print("========================================")
    print(f"[USER] {question}")

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[store.name]
                    )
                )
            ],
        ),
    )

    print("\n[OPTIBOT]")
    print(response.text)

    print("\n========================================")
    print("GROUNDING METADATA")
    print("========================================")

    if response.candidates:
        metadata = response.candidates[0].grounding_metadata

        if metadata and metadata.grounding_chunks:
            print("\n[RETRIEVED SOURCES]")

            seen = set()

            for chunk in metadata.grounding_chunks:
                if chunk.retrieved_context:
                    title = chunk.retrieved_context.title
                    store_name = chunk.retrieved_context.file_search_store

                    key = (store_name, title)

                    if key not in seen:
                        seen.add(key)

                        print(f"Store : {store_name}")
                        print(f"File  : {title}")


# ============================================================
# 7. Main
# ============================================================

if __name__ == "__main__":

    store = get_or_create_store()

    upload_articles(store)

    verify_store(store)

    sanity_check(store)