# Postgres + pgvector with hybrid search as the only vector store

Chunks, their embeddings and their full-text index live in the main Postgres database (pgvector plus `tsvector`). Results are fused with reciprocal rank fusion. We chose this over a separate vector database (OpenSearch Serverless, Qdrant, Pinecone) because it means one datastore to run and test, Document deletion that cascades in one transaction, and Project isolation enforced by an ordinary `project_id` filter. A dedicated engine would only pay off at a scale this product doesn't need.
