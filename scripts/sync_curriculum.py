import argparse
import hashlib
from pathlib import Path
import sys

from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from amba_ai.config import (
    SOVEREIGN_KB_DIR,
    EMBEDDING_MODEL_NAME,
    MAX_CHUNK_TOKENS,
    CHUNK_OVERLAP,
)
from amba_ai.logger import logger


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_documents(source: Path):
    docs = []

    for file in source.rglob("*"):
        try:
            if file.suffix.lower() == ".pdf":
                docs.extend(PyPDFLoader(str(file)).load())
            elif file.suffix.lower() == ".docx":
                docs.extend(Docx2txtLoader(str(file)).load())
        except Exception as e:
            logger.warning(f"Failed to load {file}: {e}")

    return docs


def sync_sovereign_kb(source_dir: str):
    source = Path(source_dir)

    if not source.exists():
        logger.error("Source directory not found.")
        sys.exit(1)

    logger.info("Scanning documents...")
    docs = load_documents(source)

    if not docs:
        logger.warning("No documents found.")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_CHUNK_TOKENS,
        chunk_overlap=CHUNK_OVERLAP,
    )

    chunks = splitter.split_documents(docs)

    for chunk in chunks:
        chunk.metadata["chunk_id"] = hash(chunk.page_content)

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)

    if SOVEREIGN_KB_DIR.exists():
        logger.info("Loading existing index...")
        db = FAISS.load_local(str(SOVEREIGN_KB_DIR), embeddings)
        db.add_documents(chunks)
    else:
        db = FAISS.from_documents(chunks, embeddings)

    db.save_local(str(SOVEREIGN_KB_DIR))

    logger.info(f"Sovereign KB updated: {len(chunks)} chunks added.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", "-s", required=True)

    args = parser.parse_args()
    sync_sovereign_kb(args.source)