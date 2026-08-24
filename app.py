"""Streamlit UI: upload documents, ask a question, get a grounded, cited answer
(or an honest "I don't know" when the documents don't cover it)."""

import tempfile
from pathlib import Path

import streamlit as st

from rag.answer import build_answer
from rag.chunking import chunk_text
from rag.loaders import load_file
from rag.store import VectorStore

st.set_page_config(page_title="Ask my Contracts", page_icon="📄")

# Long, unbroken filenames (e.g. an uploaded PDF name) would otherwise overflow
# their column; force wrapping so the two columns never overlap.
st.markdown(
    "<style>[data-testid='stMarkdownContainer'] * { overflow-wrap: anywhere; }</style>",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_store() -> VectorStore:
    # Cached so the embedding model loads once per session.
    return VectorStore()


store = get_store()

st.title("📄 Ask my Contracts")
st.caption(
    "A tiny local RAG app. It answers only from the documents you upload, "
    "cites the source, and says *I don't know* when the answer isn't there."
)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K = 4

# --- Sidebar: ingestion controls -------------------------------------------
with st.sidebar:
    st.header("1. Ingest documents")

    uploaded = st.file_uploader(
        "Upload contract files",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
    )

    col_a, col_b = st.columns(2)
    if col_a.button("Ingest", type="primary", use_container_width=True):
        if not uploaded:
            st.warning("Upload at least one file first.")
        else:
            total_chunks = 0
            with st.spinner("Reading, chunking and embedding…"):
                for uf in uploaded:
                    suffix = Path(uf.name).suffix
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=suffix
                    ) as tmp:
                        tmp.write(uf.getbuffer())
                        tmp_path = tmp.name

                    raw = load_file(tmp_path)
                    chunks = chunk_text(
                        raw,
                        source=uf.name,
                        chunk_size=CHUNK_SIZE,
                        overlap=CHUNK_OVERLAP,
                    )
                    store.add_chunks(chunks)
                    total_chunks += len(chunks)

            st.success(f"Ingested {len(uploaded)} file(s) → {total_chunks} chunks.")

    if col_b.button("Reset DB", use_container_width=True):
        store.reset()
        st.success("Cleared the vector store.")

    st.metric("Chunks in store", store.count())

# --- Main: ask a question ---------------------------------------------------
st.header("2. Ask a question")

# Toggle semantic vs. hybrid retrieval to compare them on the same question.
mode = st.radio(
    "Search mode",
    options=["hybrid", "semantic"],
    format_func=lambda m: {
        "hybrid": "Hybrid (meaning + keywords) — new",
        "semantic": "Semantic only (baseline)",
    }[m],
    horizontal=True,
)

question = st.text_input(
    "Your question",
    placeholder="e.g. What is the notice period for termination?",
)

if st.button("Ask") and question:
    if store.count() == 0:
        st.warning("No documents ingested yet — upload some in the sidebar.")
    else:
        hits = store.search(question, top_k=TOP_K, mode=mode)
        answer = build_answer(question, hits)

        # Answer on top, retrieved chunks below — both full width. Seeing them
        # together separates retrieval failures (wrong chunks) from generation
        # failures (right chunks, bad answer).
        st.subheader("Final answer")
        # Split the bundled "Sources:" block off so the long filenames render
        # as a wrapping caption instead of overflowing the success box.
        body, _, _sources = answer.text.partition("\n\nSources:")
        if answer.answered:
            st.success(body)
            if answer.sources:
                st.caption("Sources")
                for hit in answer.sources:
                    st.caption(f"• {hit['source']} · chunk {hit['chunk_index']}")
        else:
            st.error(body)

        st.divider()

        st.subheader(f"Retrieved chunks · mode = {mode}")
        for i, hit in enumerate(hits, 1):
            label = f"{i}. {hit['source']} · chunk {hit['chunk_index']} · score {hit['score']:.3f}"
            with st.expander(label, expanded=(i == 1)):
                st.write(hit["text"])
