# Rate Limit Fix - Sequential Generation

## Problem Identified

The agent was hitting rate limits (429 errors) constantly because:

1. **Parallel generation bypassed rate limiter**: When generating subconcepts and tasks in parallel using `asyncio.gather()`, both API calls happened simultaneously, effectively bypassing the sequential rate limiting
2. **Too aggressive rate limits**: The rate limiter was set to 20 RPM with 3s delays, which was still too aggressive
3. **Token limit reached**: Daily token limit for sanitizer model was also hit

## Solution Implemented

### 1. Changed Parallel to Sequential Generation
- **Before**: Subconcepts and tasks generated in parallel using `asyncio.gather()`
- **After**: Sequential generation - subconcepts first, then tasks
- **Benefit**: Rate limiter now works correctly, ensuring only one API call at a time

### 2. Increased Rate Limit Conservatism
- **Before**: 20 RPM, 3s minimum delay, 0.5s buffer
- **After**: 15 RPM, 4s minimum delay, 2s buffer
- **Benefit**: More conservative approach reduces chance of hitting limits

### 3. Added Delay Between Sequential Calls
- Added 1 second delay between subconcepts and tasks generation
- Ensures rate limiter has time to track requests properly

## Changes Made

1. `app/agents/nodes/generate_content.py`:
   - Changed `generate_subconcepts_and_tasks()` from parallel to sequential
   - Added 1s delay between subconcepts and tasks calls

2. `app/services/groq_service.py`:
   - Increased buffer delay from 0.5s to 2.0s

3. `app/services/rate_limiter.py`:
   - Reduced max_requests from 20 to 15 RPM
   - Increased min_delay_between_requests from 3.0s to 4.0s
   - Updated both RedisRateLimiter and InMemoryRateLimiter

## Expected Behavior

- **Rate**: Maximum 15 requests per minute (one every 4 seconds minimum)
- **Sequential**: Subconcepts and tasks generated one after another
- **Reliable**: Rate limiter properly enforces limits
- **Slower but stable**: Slightly slower but won't hit rate limits

## Performance Impact

- **Before**: ~50% faster (parallel) but constant rate limit failures
- **After**: Sequential but reliable, no rate limit failures
- **Trade-off**: Acceptable - reliability over speed

## Monitoring

Watch for:
- ✅ No more 429 errors
- ✅ Consistent generation without retries
- ✅ Agent completes successfully

