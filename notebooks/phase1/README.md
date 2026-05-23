# Phase 1: Infrastructure Setup and Verification

This folder contains the materials for Phase 1 of the arXiv Paper Curator project, which focuses on setting up and verifying the complete infrastructure stack.

## Contents

### `phase1_setup.ipynb`
A comprehensive Jupyter notebook that guides students through:

1. **System Requirements and Setup**
   - Understanding each technology component and its purpose
   - Cross-platform installation instructions (Windows, macOS, Linux)
   - Prerequisites verification with automated checking

2. **Infrastructure Architecture**
   - Complete overview of the multi-service architecture
   - Understanding how Docker containers communicate
   - Data persistence and volume management concepts

<p align="center">
  <img src="../../static/phase1_infra_setup.png" alt="Phase 1 Infrastructure Setup" width="700">
</p>

**Architecture Overview:**

| Component | Type | Access |
|-----------|------|--------|
| **FastAPI** (Port 8000) | Local container | REST API with async support and automatic documentation |
| **OpenSearch 2.19** (Ports 9200, 5601) | Local container | Hybrid search engine with Dashboards UI |
| **Apache Airflow 3.0** (Port 8080) | Local container | Workflow orchestration with DAGs |
| **Neon PostgreSQL** | Cloud (serverless) | Paper metadata and content storage |
| **Upstash Redis** | Cloud (serverless) | Response caching (6-hour TTL) |
| **OpenAI API** | Cloud | LLM generation (`gpt-4o-mini`) |
| **Langfuse Cloud** | Cloud | Observability and tracing |

3. **Service-by-Service Setup**
   - Neon PostgreSQL for paper metadata storage
   - OpenSearch for full-text and vector search capabilities
   - Apache Airflow for workflow automation
   - OpenAI API for LLM inference
   - FastAPI for REST API endpoints

4. **Verification and Testing**
   - Automated health checks for all 4 local containers
   - Cloud service connectivity verification
   - Neon PostgreSQL table count check (48 Airflow metadata tables)
   - Common troubleshooting scenarios and solutions

## Learning Objectives

By completing this phase's materials, students will:

- Understand containerization and Docker Compose orchestration
- Learn how to set up a production-grade infrastructure stack
- Gain experience with cloud-managed database and caching services
- Master troubleshooting techniques for multi-service applications
- Learn direct HTTP API testing vs service abstraction layers
- Build confidence working with professional development tools

## Cloud Services Setup

Phase 1 uses four cloud-managed services in place of local containers. Sign up (all have free tiers):

### Neon PostgreSQL
1. Sign up at https://console.neon.tech
2. Create a project → Connection Details → SQLAlchemy tab
3. Copy the `postgresql+psycopg2://` URL to `.env`:
   ```
   POSTGRES_DATABASE_URL=postgresql+psycopg2://<user>:<pass>@<host>.neon.tech/neondb?sslmode=require
   ```

### OpenAI API
1. Create account at https://platform.openai.com
2. Go to API Keys → Create key
3. Add to `.env`:
   ```
   OPENAI_API_KEY=sk-proj-...
   OPENAI_MODEL=gpt-4o-mini
   ```

### Upstash Redis
1. Sign up at https://console.upstash.com
2. Create database → go to **TCP tab** (not REST)
3. Copy the `rediss://` URL to `.env`:
   ```
   REDIS__URL=rediss://default:<token>@<host>.upstash.io:6379
   REDIS__TTL_HOURS=6
   ```

### Langfuse Cloud
1. Sign up at https://cloud.langfuse.com
2. Create project → Settings → API Keys
3. Add to `.env` (**double underscore** required):
   ```
   LANGFUSE__PUBLIC_KEY=pk-lf-...
   LANGFUSE__SECRET_KEY=sk-lf-...
   LANGFUSE__HOST=https://us.cloud.langfuse.com
   ```

## Target Audience

This material is designed for:
- **Beginners** who want to learn modern software infrastructure
- **Students** looking to understand how real-world applications are built
- **Professionals** transitioning into software development or DevOps
- **Anyone** interested in building their own AI-powered research tools

## Time Commitment

- **Setup**: 2-3 hours (including software installation and cloud account setup)
- **Notebook completion**: 1 hour
- **Total**: 2-4 hours

## 📖 Additional Resources

**Phase 1 Blog Post:** [The Infrastructure That Powers RAG Systems](https://jamwithai.substack.com/p/the-infrastructure-that-powers-rag)
- Deep dive into each infrastructure component
- Production deployment considerations
- Architecture decision explanations

## Support Resources

If you encounter issues:
1. Check the troubleshooting sections in the notebook
2. Review the common problems and solutions
3. Ensure all prerequisites are properly installed
4. Follow the step-by-step verification procedures
5. Ask in Jam With AI substack chat channel

## Next Steps

After completing Phase 1, you will be ready to:
- Understand how each service contributes to the overall system
- Modify and extend the infrastructure as needed
- Proceed to Phase 2: arXiv Integration and PDF Processing
- Build confidence in working with professional development environments
