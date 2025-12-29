from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from supabase import Client
from uuid import UUID
from typing import List, Optional
import logging

from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token
from app.services.rag_pipeline import generate_rag_response

router = APIRouter(
    tags=["Chatbot"],
)

logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's message", min_length=1, max_length=2000)
    conversation_history: Optional[List[ChatMessage]] = Field(
        default=[], 
        description="Previous conversation messages for context"
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="AI assistant's response")
    chunks_used: List[dict] = Field(default=[], description="Chunks used as context")


@router.post("/{project_id}/chat")
async def chat(
    project_id: UUID,
    chat_request: ChatRequest,
    user_info: dict = Depends(verify_clerk_token),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Chat with AI tutor about a specific project.
    
    Flow:
    1. Verify Clerk token (get clerk_user_id)
    2. Get Supabase user_id from User table using clerk_user_id
    3. Verify project exists and belongs to the user
    4. Check if project has embeddings (status should be 'completed')
    5. Generate RAG response using project's chunks and embeddings
    6. Return AI response
    
    Args:
        project_id: UUID of the project to chat about
        chat_request: Contains user message and conversation history
        user_info: Authenticated user info from Clerk
        supabase: Supabase client
        
    Returns:
        ChatResponse with AI response and chunks used
    """
    try:
        clerk_user_id = user_info["clerk_user_id"]
        logger.info(f"💬 Chat request for project_id={project_id} from user: {clerk_user_id}")
        
        # Get user_id
        user_response = supabase.table("User").select("id").eq("clerk_user_id", clerk_user_id).execute()
        
        if not user_response.data or len(user_response.data) == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user_response.data[0]["id"]
        
        # Verify project exists and belongs to the user
        project_response = supabase.table("Projects").select(
            "project_id, project_name, status, user_id"
        ).eq("project_id", str(project_id)).execute()
        
        if not project_response.data or len(project_response.data) == 0:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = project_response.data[0]
        
        # Verify project ownership
        if project["user_id"] != user_id:
            raise HTTPException(
                status_code=403, 
                detail="You don't have permission to access this project"
            )
        
        project_status = project.get("status")
        project_name = project.get("project_name", "Unknown")
        
        logger.info(f"   Project found: {project_name} (status: {project_status})")
        
        # Check if project has embeddings
        if project_status != "ready":
            raise HTTPException(
                status_code=400,
                detail=f"Project embeddings are not ready yet. Current status: {project_status}. "
                       f"Please wait for the embedding pipeline to complete."
            )
        
        # Validate conversation history format
        conversation_history = []
        if chat_request.conversation_history:
            for msg in chat_request.conversation_history:
                if msg.role not in ["user", "assistant"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid message role: {msg.role}. Must be 'user' or 'assistant'"
                    )
                conversation_history.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Limit conversation history to last 10 messages to avoid token limits
        if len(conversation_history) > 10:
            conversation_history = conversation_history[-10:]
            logger.debug(f"   Limited conversation history to last 10 messages")
        
        # Generate RAG response
        try:
            logger.info(f"   Generating RAG response for message: {chat_request.message[:100]}...")
            rag_result = await generate_rag_response(
                project_id=str(project_id),
                query=chat_request.message,
                conversation_history=conversation_history
            )
            
            logger.info(f"✅ Successfully generated response (used {len(rag_result.get('chunks_used', []))} chunks)")
            
            return ChatResponse(
                response=rag_result["response"],
                chunks_used=rag_result.get("chunks_used", [])
            )
            
        except ValueError as e:
            # Handle cases where no chunks are found
            logger.warning(f"⚠️  RAG generation failed: {e}")
            raise HTTPException(
                status_code=404,
                detail=str(e)
            )
        except Exception as e:
            logger.error(f"❌ Error generating RAG response: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate response: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat request failed: {str(e)}")