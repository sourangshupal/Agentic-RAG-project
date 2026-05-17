# Phase 4: Chunking & Hybrid Search

Phase 4 adds two major capabilities: intelligent text chunking of papers into retrievable segments, and semantic vector search fused with BM25 via Reciprocal Rank Fusion (RRF).

---

## 1. Document Indexing Pipeline

This pipeline runs inside Airflow Task 3 (`index_papers_hybrid`) for every paper stored in PostgreSQL.

```mermaid
flowchart TD
    PG[(PostgreSQL\nPaper record\nraw_text + sections)] --> CHUNKER

    subgraph CHUNKER["TextChunker — src/services/indexing/text_chunker.py"]
        SC{sections\navailable?}
        SC -->|yes| SB[Section-based chunking\npreferred strategy]
        SC -->|no| WB[Word-based fallback\n600 words / 100 word overlap]
    end

    SB --> CHUNKS[List of TextChunk\ntext, chunk_index\nsection_title\nword_count, offsets]
    WB --> CHUNKS

    CHUNKS --> BATCH[Batch texts\n100 chunks per API call]
    BATCH --> JINA[Jina AI\nPOST https://api.jina.ai/v1/embeddings\nmodel: jina-embeddings-v3\ntask: retrieval.passage\ndimensions: 1024]
    JINA --> VECTORS[List of 1024-dim vectors]

    CHUNKS & VECTORS --> BULK[OpenSearch\nbulk_index_chunks\nindex: arxiv-papers-chunks]
    BULK --> DOC["Indexed Document\nchunk_text\nembedding: 1024-dim float\narxiv_id, title, authors\nchunk_index, section_title\nword_count, published_date"]
```

---

## 2. TextChunker — Chunking Strategy Decision Tree

```mermaid
flowchart TD
    INPUT[Paper sections + raw_text] --> PARSE[Parse sections\nhandles dict / JSON string / list]
    PARSE --> FILTER[Filter out\nmetadata sections\nduplicate abstracts\ncontent under 30 words with email/affiliation patterns]
    FILTER --> HEADER[Build header\ntitle + Abstract text]
    HEADER --> LOOP[For each section]

    LOOP --> WC{Section\nword count}
    WC -->|100 to 800 words| SINGLE["Single chunk\nheader + section content\nsection_title preserved"]
    WC -->|less than 100 words| BUFFER["Buffer section\ncombine with adjacent sections\nuntil >= min_chunk_size"]
    WC -->|more than 800 words| SPLIT["Word-based split\n600w chunks, 100w overlap\nsection context in each chunk"]

    SINGLE & BUFFER & SPLIT --> OUT[TextChunk list]
    OUT --> FALLBACK{any chunks\nproduced?}
    FALLBACK -->|no| WB_FB[Word-based fallback\non full raw_text]
    FALLBACK -->|yes| DONE([Return chunks])
    WB_FB --> DONE
```

---

## 3. Hybrid Query Flow (BM25 + Vector + RRF)

When `use_hybrid=true`, the search endpoint generates an embedding for the query and executes a hybrid search.

```mermaid
flowchart TD
    CLIENT2[Client\nPOST /api/v1/hybrid-search/\nuse_hybrid=true] --> ROUTER2[hybrid_search.py]
    ROUTER2 --> EMBED_Q[JinaEmbeddingsClient\nembed_query\ntask: retrieval.query\ndimensions: 1024]
    EMBED_Q --> Q_VEC[Query vector\n1024-dim float list]

    Q_VEC --> SEARCH[OpenSearchClient\nsearch_unified\nuse_hybrid=True]
    SEARCH --> BM25Q[BM25 multi_match query\nchunk_text^3 / title^2 / abstract^1]
    SEARCH --> KNNQ[KNN query\nembedding field\ncosine similarity\nk = size * hybrid_search_size_multiplier]

    BM25Q & KNNQ --> RRF_PIPE[RRF Pipeline\nhybrid-rrf-pipeline\nrank_constant = 60\nwindow_size = 100]
    RRF_PIPE --> FUSED[Fused result set\nRRF score = sum of 1 divided by rank_constant + rank_i]
    FUSED --> FILTER2[Apply filters\ncategories, min_score]
    FILTER2 --> RESP3[SearchResponse\nsearch_mode: hybrid]
```

---

## 4. RRF Score Formula

```mermaid
flowchart LR
    BM25R["BM25 rank (r_bm25)"] --> RRF_F
    KNNR["KNN rank (r_knn)"] --> RRF_F
    RRF_F["RRF Score =\n1 / (60 + r_bm25) + 1 / (60 + r_knn)"]
    RRF_F --> FINAL[Final merged ranking]
```

Both sub-queries contribute equally. A document ranked 1st in BM25 but not found by KNN still scores `1/(60+1) ≈ 0.016`. Appearing in both lists compounds the score.

---

## 5. OpenSearch Index — Full Mapping

```mermaid
flowchart TD
    IDX2["arxiv-papers-chunks"] --> TXT["Text (analyzed)\nchunk_text\ntitle\nabstract\nauthors\nsection_title"]
    IDX2 --> KW["Keyword (exact)\nchunk_id\narxiv_id\npaper_id\ncategories"]
    IDX2 --> VEC["knn_vector\nembedding\n1024 dimensions\nspace_type: cosine\nalgorithm: HNSW\nef_construction: 512 / m: 16"]
    IDX2 --> NUM["Numeric / Date\nchunk_index\nchunk_word_count\npublished_date\ncreated_at / updated_at"]
    IDX2 --> STR["Metadata strings\nembedding_model\npaper_id (keyword)"]
```
