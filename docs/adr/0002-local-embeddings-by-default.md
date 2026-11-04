# Local embedding model by default, provider embeddings optional

Every Project embeds with a platform-run local model (CPU, ONNX via `fastembed`) unless it opts into a provider (Voyage, OpenAI or Bedrock) using one of the Organisation's Provider Credentials. The default can't be a provider because Anthropic, a likely chat provider, has no embeddings API. A local default also means a new Organisation can upload Documents before configuring any credential, and tests are deterministic. The Embedding Model is recorded against every Chunk, so a Project's vectors are never silently mixed across models.

The default local model is `multilingual-e5-small`. A Project can change its Embedding Model at any time. A background re-embed builds the new vectors alongside the old ones, which keep serving until the job finishes, and then the Project switches over in one step.
