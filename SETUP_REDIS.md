# Redis Setup for Rate Limiting

This application uses Redis for distributed rate limiting to prevent hitting LLM API rate limits.

## Option 1: Local Redis (Recommended for Development)

### Install Redis

**Windows:**
1. Download Redis from: https://github.com/microsoftarchive/redis/releases
2. Or use WSL: `sudo apt-get install redis-server`
3. Or use Docker: `docker run -d -p 6379:6379 redis:alpine`

**macOS:**
```bash
brew install redis
brew services start redis
```

**Linux:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

### Configure

Add to your `.env` file:
```
REDIS_URL=redis://localhost:6379/0
```

## Option 2: Redis Cloud (Free Tier Available)

1. Sign up at https://redis.com/try-free/
2. Create a free database
3. Copy the connection URL
4. Add to your `.env` file:
```
REDIS_URL=redis://default:password@host:port
```

## Option 3: No Redis (Fallback)

If Redis is not configured, the application will automatically use an in-memory rate limiter. This works for single-instance deployments but won't coordinate across multiple workers.

**No configuration needed** - the app will detect missing Redis and use fallback.

## Testing Redis Connection

The application will log on startup:
- `✅ Redis connected for rate limiting` - Redis is working
- `⚠️ Failed to connect to Redis: ..., using in-memory rate limiter` - Using fallback

## Rate Limit Configuration

The rate limiter is configured to:
- **Max requests:** 28 per minute (leaves buffer below 30 RPM limit)
- **Window:** 60 seconds
- **Automatic retry:** With exponential backoff

This prevents hitting Groq's 30 requests-per-minute limit.

