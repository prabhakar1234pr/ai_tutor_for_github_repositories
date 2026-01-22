# Gemini Chatbot Test

A simple HTML chatbot interface to test your Gemini API integration.

## Features

- 🎨 Beautiful, modern UI
- 🔄 Two API methods:
  - **Direct API Key**: Call Gemini API directly (uses your API key)
  - **Backend API**: Call through your FastAPI backend (uses service account with GCP free credits)
- 💬 Real-time chat interface
- 📱 Responsive design
- 🎯 Simple markdown formatting support

## How to Use

### Option 1: Direct API Key Method

1. Open `gemini_chatbot.html` in your browser
2. Select "Direct API Key (Gemini API)" from the dropdown
3. Enter your Gemini API key (or create one from [Google AI Studio](https://makersuite.google.com/app/apikey))
4. Select your preferred model (gemini-pro, gemini-1.5-pro, etc.)
5. Start chatting!

**Note**: Your API key will be saved in browser localStorage for convenience.

### Option 2: Backend API Method (Uses GCP Free Credits)

1. Make sure your backend server is running:
   ```bash
   cd ai_tutor_for_github_repositories
   python -m uvicorn app.main:app --reload
   ```

2. Open `gemini_chatbot.html` in your browser

3. Select "Backend API (FastAPI)" from the dropdown

4. Enter your backend URL (default: `http://localhost:8000`)

5. Start chatting! The backend will use your service account JSON and GCP free credits.

## Backend Endpoint

The chatbot uses the `/api/chatbot/test` endpoint which:
- ✅ No authentication required (for testing only)
- ✅ Uses your Gemini service account (GCP free credits)
- ✅ Supports conversation history
- ✅ Returns AI responses

## Testing Your Setup

### Test Direct API Key
1. Get an API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Use "Direct API Key" method in the chatbot
3. Send a test message like "Say hello!"

### Test Backend Integration
1. Ensure your `.env` has:
   ```bash
   GOOGLE_APPLICATION_CREDENTIALS=credentials/gitguide-backend-5d3d36f67a0c.json
   GCP_PROJECT_ID=gitguide-backend
   GCP_LOCATION=us-central1
   ```

2. Start your backend server

3. Use "Backend API" method in the chatbot

4. Send a test message

5. Check backend logs to see:
   - ✅ "Using Gemini with Service Account (uses GCP free credits)"
   - ✅ Response generation logs

## Verify GCP Credits Usage

1. Go to [GCP Console Billing](https://console.cloud.google.com/billing)
2. Check your usage - you should see Gemini API charges deducted from your $300 free credits

## Troubleshooting

### "API key not found" error
- Make sure you've entered your API key correctly
- For backend method, ensure your `.env` is configured

### "Service account file not found" error
- Check that `GOOGLE_APPLICATION_CREDENTIALS` path in `.env` is correct
- Verify the JSON file exists at that path

### "Project ID not found" error
- Set `GCP_PROJECT_ID` in your `.env` file
- Or ensure `project_id` is in your service account JSON

### CORS errors (when using backend)
- Make sure your backend CORS settings allow requests from `file://` protocol
- Or serve the HTML file through a local web server

## File Structure

```
tests/html/
├── gemini_chatbot.html  # Main chatbot interface
└── README.md            # This file
```

## Notes

- The chatbot saves your API key in browser localStorage (for convenience only)
- For production, never expose API keys in frontend code
- The test endpoint (`/api/chatbot/test`) is for testing only - add authentication for production use
