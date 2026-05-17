# Phase 2: Data Ingestion Pipeline

Phase 2 adds the automated data pipeline that fetches arXiv papers daily, parses their PDFs, and stores structured content in PostgreSQL. All orchestration is handled by Apache Airflow.

---

## 1. Airflow DAG — Task Dependency Chain

**Schedule:** `0 6 * * 1-5` (Monday–Friday, 6 AM UTC)  
**DAG ID:** `arxiv_paper_ingestion`  
**Max active runs:** 1 (no parallel runs)

```mermaid
flowchart TD
    START([DAG Triggered]) --> T1

    T1["Task 1: setup_environment\nVerify DB connection\nVerify OpenSearch health\nsetup_indices if not exist\nVerify arXiv client ready"]

    T2["Task 2: fetch_daily_papers\nFetch metadata from arXiv API\nDownload PDFs concurrently\nParse with Docling\nUpsert to PostgreSQL\nXCom push: fetch_results"]

    T3["Task 3: index_papers_hybrid\nPull processed papers from PostgreSQL\nChunk text via TextChunker\nGenerate Jina AI embeddings\nBulk index to OpenSearch\nXCom push: hybrid_index_stats"]

    T4["Task 4: generate_daily_report\nPull XCom from tasks 2 and 3\nAggregate fetch + index + DB stats\nLog JSON report\nXCom push: daily_report"]

    T5["Task 5: cleanup_temp_files\nBashOperator\nfind /tmp -name '*.pdf' -mtime +30 -delete"]

    T1 --> T2 --> T3 --> T4 --> T5
```

---

## 2. Task 2 Detail — Paper Fetching & Processing

```mermaid
flowchart TD
    START2([fetch_daily_papers starts]) --> DATE[Determine target date\nexecution_date - 1 day\nformat: YYYYMMDD]
    DATE --> ARXIV_API[arXiv API\nmax_results from config\ncategory: cs.AI\nrate_limit_delay: 3s between requests]
    ARXIV_API --> META[Extract metadata\narxiv_id, title, authors\nabstract, categories\npublished_date, pdf_url]
    META --> PDF_DL[Download PDFs\n5 concurrent workers\nretry logic on failure]
    PDF_DL --> DOCLING[Docling Parser\nExtract raw_text\nExtract sections\nparser_metadata stored]
    DOCLING --> PG_UPSERT[(Neon PostgreSQL\nupsert Paper record\narxiv_id as unique key)]
    PG_UPSERT --> XCOM[XCom push\npapers_fetched\npapers_stored\ntarget_date]
```

---

## 3. Task 3 Detail — Hybrid Indexing

```mermaid
flowchart TD
    START3([index_papers_hybrid starts]) --> PULL[XCom pull: fetch_results\nget papers_stored count]
    PULL --> QUERY_PG[Query PostgreSQL\nget recently processed papers\nlimit = papers_stored]
    QUERY_PG --> CHUNK[TextChunker\nsection-based chunking preferred\n600 words / 100 word overlap\nsee phase4 for chunking detail]
    CHUNK --> EMBED[Jina AI\nembed_passages\nmodel: jina-embeddings-v3\n1024 dimensions\nbatch size: 100]
    EMBED --> BULK[OpenSearch\nbulk_index_chunks\nindex: arxiv-papers-chunks\nstores chunk_text + embedding + metadata]
    BULK --> STATS[Compute stats\npapers_processed\ntotal_chunks_created\ntotal_chunks_indexed]
    STATS --> XCOM2[XCom push\nhybrid_index_stats]
```

---

## 4. PostgreSQL Paper Schema

```mermaid
erDiagram
    PAPER {
        UUID id PK
        string arxiv_id UK
        string title
        json authors
        text abstract
        json categories
        datetime published_date
        string pdf_url
        text raw_text
        json sections
        json references
        string parser_used
        json parser_metadata
        bool pdf_processed
        datetime pdf_processing_date
        datetime created_at
        datetime updated_at
    }
```

---

## 5. Daily Report Structure

Task 4 assembles a JSON report from XCom data of previous tasks:

```mermaid
flowchart LR
    T2X[XCom: fetch_results\npapers_fetched\npapers_stored\ntarget_date] --> REPORT[Daily Report JSON]
    T3X[XCom: hybrid_index_stats\npapers_processed\nchunks_created\nchunks_indexed\nembeddings_generated] --> REPORT
    DB_COUNT[PostgreSQL\ntotal papers count] --> REPORT
    OS_COUNT[OpenSearch\ndocument count\nindex size MB] --> REPORT
    REPORT --> STATUS{pipeline_status}
    STATUS -->|all tasks OK| SUCCESS[success]
    STATUS -->|partial data| PARTIAL[partial]
    STATUS -->|errors| ERROR[error]
```
