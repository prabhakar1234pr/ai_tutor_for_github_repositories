import logging
import time
from typing import List, Dict, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

# Groq API endpoint (OpenAI-compatible)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Lazy singleton instance
_groq_service_instance = None


def get_groq_service() -> 'GroqService':
    """
    Get or create singleton GroqService instance (lazy initialization).
    
    Returns:
        GroqService: Singleton instance
    """
    global _groq_service_instance
    
    if _groq_service_instance is None:
        logger.info(f"🤖 Initializing GroqService (first use)...")
        logger.info(f"   Model: {settings.groq_model}")
        _groq_service_instance = GroqService()
        logger.info(f"✅ GroqService ready (will reuse for future requests)")
    
    return _groq_service_instance


class GroqService:
    def __init__(self):
        """
        Initialize GroqService.
        """
        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is not configured. Please set it in your .env file."
            )
        
        self.api_key = settings.groq_api_key
        self.model = settings.groq_model
        self.api_url = GROQ_API_URL
        self.timeout = 60.0  # 60 seconds timeout
        
        logger.info(f"✅ GroqService initialized")
        logger.debug(f"   API URL: {self.api_url}")
        logger.debug(f"   Model: {self.model}")
        logger.debug(f"   Timeout: {self.timeout}s")

    def generate_response(
        self,
        user_query: str,
        system_prompt: str,
        context: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:
        """
        Generate a response using Groq API with RAG context.
        
        Args:
            user_query: The user's question
            system_prompt: System instructions for the AI
            context: Retrieved chunks from codebase as context
            conversation_history: Previous messages [{"role": "user|assistant", "content": "..."}]
            
        Returns:
            Generated response string
            
        Raises:
            ValueError: If API key is missing or invalid
            httpx.HTTPError: If API request fails
        """
        if conversation_history is None:
            conversation_history = []
        
        start_time = time.time()
        logger.info(f"🤖 Generating response with Groq API (model: {self.model})")
        logger.debug(f"   User query length: {len(user_query)} chars")
        logger.debug(f"   Context length: {len(context)} chars")
        logger.debug(f"   Conversation history: {len(conversation_history)} messages")
        
        # Build messages array for Groq API
        messages = []
        
        # Add system prompt
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # Add context as a system message (or user message)
        if context:
            context_message = (
                f"Here is the relevant context from the codebase:\n\n{context}\n\n"
                f"Please answer the user's question based on this context. "
                f"If the answer cannot be found in the context, say so."
            )
            messages.append({
                "role": "system",
                "content": context_message
            })
        
        # Add conversation history
        for msg in conversation_history:
            if msg.get("role") in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # Add current user query
        messages.append({
            "role": "user",
            "content": user_query
        })
        
        # Prepare API request
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000,
            "top_p": 1.0,
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        logger.debug(f"   Request payload: model={self.model}, messages={len(messages)}, max_tokens={payload['max_tokens']}")
        
        # Make API request
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                
                result = response.json()
                
                # Extract response text
                if "choices" not in result or len(result["choices"]) == 0:
                    raise ValueError("No choices returned from Groq API")
                
                assistant_message = result["choices"][0]["message"]["content"]
                
                # Log usage info if available
                if "usage" in result:
                    usage = result["usage"]
                    logger.debug(
                        f"   Token usage: prompt={usage.get('prompt_tokens', 0)}, "
                        f"completion={usage.get('completion_tokens', 0)}, "
                        f"total={usage.get('total_tokens', 0)}"
                    )
                
                duration = time.time() - start_time
                logger.info(f"✅ Generated response ({len(assistant_message)} chars) in {duration:.3f}s")
                
                return assistant_message
                
        except httpx.HTTPStatusError as e:
            error_msg = f"Groq API HTTP error: {e.response.status_code}"
            if e.response.status_code == 401:
                error_msg += " - Invalid API key"
            elif e.response.status_code == 429:
                error_msg += " - Rate limit exceeded"
            elif e.response.status_code == 500:
                error_msg += " - Groq API server error"
            
            try:
                error_detail = e.response.json()
                if "error" in error_detail:
                    error_msg += f" - {error_detail['error'].get('message', '')}"
            except:
                error_msg += f" - {e.response.text[:200]}"
            
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg) from e
            
        except httpx.TimeoutException:
            error_msg = f"Groq API request timed out after {self.timeout}s"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
            
        except httpx.RequestError as e:
            error_msg = f"Groq API request failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg) from e
            
        except Exception as e:
            error_msg = f"Unexpected error calling Groq API: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            raise ValueError(error_msg) from e