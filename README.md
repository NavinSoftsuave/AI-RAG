# 📄 Ask my Contracts — a tiny local RAG app

A minimal **Retrieval-Augmented Generation** app for the *Legal Contracts* task.
Upload contract PDFs, ask a question, and get an answer drawn **only** from your
documents — with a citation. If the answer isn't in the documents, it says
*"I don't know"* instead of making one up.

Runs **fully locally** — no API key, no internet needed after the first model
download.

## How it works

```
Ingest:   load file  ->  split into chunks  ->  embed each chunk  ->  store vectors
Ask:      embed question  ->  find nearest chunks  ->  check similarity  ->  answer + cite
```

- **Load** ([rag/loaders.py](rag/loaders.py)) — read text from PDF / TXT / MD.
- **Chunk** ([rag/chunking.py](rag/chunking.py)) — cut each document into small
  overlapping windows so each vector captures one focused idea.
- **Embed + store** ([rag/store.py](rag/store.py)) — `BAAI/bge-small-en-v1.5`
  turns text into vectors; **Chroma** stores them and does fast nearest-neighbour
  search (HNSW index, cosine similarity).
- **Answer** ([rag/answer.py](rag/answer.py)) — return the best-matching passage
  with its source. If the top match is below a similarity threshold, refuse.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Run the web app

```bash
./venv/bin/streamlit run app.py
```

Then in the browser: upload your contract files in the sidebar → **Ingest** →
type a question → **Ask**. The *Retrieved chunks* panel shows exactly what the
app searched and each chunk's similarity score.

## Or use the command line

```bash
# put your PDFs in docs/, then:
./venv/bin/python ingest_cli.py docs/ --reset --chunk-size 800 --overlap 150
```

## Things to try (part of the task)

- **Compare chunk sizes.** Ingest at `--chunk-size 400`, run your questions,
  `--reset`, then re-ingest at `1200` and compare. Small chunks = precise but
  fragmented; large chunks = more context but fuzzier matches.
- **Prove the refusal.** Ask something the contracts don't cover — it should
  say *I don't know*. Tune `MIN_SIMILARITY` in [rag/answer.py](rag/answer.py)
  if it's too strict or too lenient for your documents.
- **Check citations.** Every answer names the source document and chunk.

## Project layout

```
app.py            Streamlit UI
ingest_cli.py     command-line ingestion
rag/
  loaders.py      PDF / text loading
  chunking.py     chunk size + overlap
  store.py        embeddings + Chroma vector store
  answer.py       grounded answer + "I don't know"
docs/             put your contract files here
```
