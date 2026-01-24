# Embedding Model Error Fix

## Error
```
404 GET .../publishers/google/models/gemini-embedding-001: Publisher Model `publishers/google/models/gemini-embedding-001` is not found.
```

## Cause
The model `gemini-embedding-001` may not be available in your GCP project/region, or requires specific API enablement.

## Solutions

### Option 1: Use a Different Vertex AI Model (Recommended for GCP)
Change `EMBEDDING_MODEL_NAME` in your `.env` file:

```env
# Use textembedding-gecko@003 (more widely available)
EMBEDDING_MODEL_NAME=textembedding-gecko@003

# Or try text-embedding-005
EMBEDDING_MODEL_NAME=text-embedding-005
```

### Option 2: Switch to OpenAI Embeddings (Easiest for Local Dev)
Change `EMBEDDING_PROVIDER` in your `.env` file:

```env
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key
EMBEDDING_MODEL_NAME=text-embedding-3-small  # or text-embedding-3-large
```

### Option 3: Use Local Embeddings (No API Costs)
Change `EMBEDDING_PROVIDER` in your `.env` file:

```env
EMBEDDING_PROVIDER=local
# Uses sentence-transformers locally (slower but free)
```

### Option 4: Enable Gemini Embedding API in GCP
If you want to use `gemini-embedding-001`:

1. Go to [GCP Console](https://console.cloud.google.com/vertex-ai/publishers/google/model-garden)
2. Enable the Vertex AI API
3. Enable the Gemini API
4. Ensure your service account has proper permissions

## Current Fix Applied
I've updated the default model name to `textembedding-gecko@003` which is more widely available.

To apply: Restart your containers:
```bash
docker-compose restart api roadmap workspaces
```
