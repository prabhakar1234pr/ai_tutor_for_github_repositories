# Update .env for gemini-embedding-001

## Required Changes

Update your `.env` file:

```env
# Change this (if it exists):
GCP_LOCATION=global

# To this:
GCP_LOCATION=us-central1

# The embedding model is now set to:
EMBEDDING_MODEL_NAME=gemini-embedding-001
```

## Why

1. ✅ `gemini-embedding-001` is a better, newer model
2. ✅ It works with `us-central1` region (tested successfully)
3. ❌ It does NOT work with `global` region (causes 404)

## After Updating .env

Rebuild and restart containers:

```powershell
# Rebuild to get the new model name
docker-compose build api roadmap workspaces

# Restart
docker-compose restart api roadmap workspaces

# Check logs
docker-compose logs -f api | Select-String -Pattern "embedding|Vertex AI"
```

## Expected Success Message

You should see:
```
✅ Vertex AI embeddings initialized: gemini-embedding-001
```

## Model Comparison

| Model | Dimensions | Max Tokens | Quality | Notes |
|-------|-----------|------------|---------|-------|
| `gemini-embedding-001` | Up to 3,072 | 2,048 | ⭐⭐⭐⭐⭐ | State-of-the-art, supports English, multilingual, and code |
| `textembedding-gecko@003` | 768 | 3,072 | ⭐⭐⭐⭐ | Older but widely available |
| `text-embedding-005` | Up to 768 | 2,048 | ⭐⭐⭐⭐ | Specialized for English and code |

`gemini-embedding-001` is the best choice! 🎉
