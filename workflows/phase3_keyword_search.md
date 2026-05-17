# Phase 3: Keyword Search — BM25

Phase 3 introduces the first search endpoint using BM25 — the classic probabilistic ranking algorithm. This is the search foundation that every production RAG system needs before adding semantic layers.

---

## 1. BM25 Request Flow

```mermaid
flowchart LR
    CLIENT[Client] -->|POST /api/v1/hybrid-search/\nuse_hybrid=false| ROUTER[hybrid_search.py]
    ROUTER --> DEP[Inject dependencies\nOpenSearchClient\nJinaEmbeddingsClient]
    DEP --> CHECK{use_hybrid?}
    CHECK -->|false| BM25_PATH[search_unified\nno embedding generated\nuse_hybrid=False]
    CHECK -->|true| HYBRID_PATH[see Phase 4]
    BM25_PATH --> QB[QueryBuilder.build\nBM25 only]
    QB --> OS[(OpenSearch\narxiv-papers-chunks)]
    OS --> HITS[Ranked hits\nBM25 score]
    HITS --> RESP[SearchResponse\nquery, total, hits, search_mode='bm25']
    RESP --> CLIENT
```

---

## 2. QueryBuilder Internals

The `QueryBuilder` (`src/services/opensearch/query_builder.py`) assembles the full OpenSearch request body.

```mermaid
flowchart TD
    BUILD["QueryBuilder.build()"] --> Q["_build_query()\nmulti_match\nfields: chunk_text^3, title^2, abstract^1\ntype: best_fields\noperator: or\nfuzziness: AUTO\nprefix_length: 2"]
    BUILD --> F["_build_filters()\nterms query on categories\nif categories param provided"]
    BUILD --> SRC["_build_source_fields()\nexcludes: embedding field\navoids returning 1024-dim vectors"]
    BUILD --> HL["_build_highlight()\npre_tags: mark\npost_tags: /mark\nfragment_size per field"]
    BUILD --> SORT["_build_sort()\nNone = relevance order\nor published_date desc + _score"]

    Q & F & SRC & HL & SORT --> BODY[Final OpenSearch\nrequest body]
```

---

## 3. OpenSearch Index Structure (Phase 3 view)

At Phase 3, only the text fields are used. The `embedding` field exists in the mapping (added in Phase 4) but is not yet populated.

```mermaid
flowchart TD
    IDX["Index: arxiv-papers-chunks"] --> TF["Text Fields\nchunk_text — analyzed, BM25\ntitle — analyzed\nabstract — analyzed\nauthors — analyzed"]
    IDX --> KF["Keyword Fields\nchunk_id\narxiv_id\npaper_id\ncategories\nsection_title"]
    IDX --> NF["Numeric / Date Fields\nchunk_index\nchunk_word_count\npublished_date\ncreated_at"]
    IDX --> VF["Vector Field\nembedding — knn_vector 1024-dim\nHNSW algorithm\nnot used in Phase 3"]

    BM25_Q[BM25 Query] -->|searches| TF
    BM25_Q -->|filters on| KF
```

---

## 4. SearchHit Response Shape

```mermaid
flowchart LR
    OS_HIT[OpenSearch Hit] --> SH[SearchHit\narxiv_id\ntitle\nauthors\nabstract\npublished_date\npdf_url\nscore: float\nhighlights: dict\nchunk_text: str\nchunk_id: str\nsection_name: str]
    SH --> RESP2[SearchResponse\nquery: str\ntotal: int\nhits: SearchHit list\nsize: int\nfrom_: int\nsearch_mode: bm25]
```

---

## 5. Search Modes Supported at This Endpoint

```mermaid
flowchart LR
    EP[POST /api/v1/hybrid-search/] --> M1["use_hybrid=false\nlatest_papers=false\nBM25 ranked by relevance"]
    EP --> M2["use_hybrid=false\nlatest_papers=true\nBM25 + sort by published_date desc"]
    EP --> M3["use_hybrid=true\nPhase 4 — adds vector search"]
    EP --> M4["min_score=0.5\nFilter low-confidence results"]
```
