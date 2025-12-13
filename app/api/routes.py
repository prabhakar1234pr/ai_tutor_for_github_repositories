from fastapi import APIRouter
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/route1")
def route_one():
    """Button One endpoint"""
    logger.info("Route 1 called")
    return {
        "message": "✅ You successfully called Route 1!",
        "button": "Button One",
        "data": "This is data from the backend"
    }

@router.get("/route2")
def route_two():
    """Button Two endpoint"""
    logger.info("Route 2 called")
    return {
        "message": "✅ You successfully called Route 2!",
        "button": "Button Two",
        "data": "Backend is working perfectly!"
    }

@router.get("/hello")
def say_hello():
    """Button Four endpoint"""
    logger.info("Hello endpoint called")
    return {
        "message": "👋 Hello from API routes!",
        "status": "connected",
        "backend": "FastAPI"
    }

@router.get("/health")
def health_check():
    """Button Three - Health check endpoint"""
    return {
        "status": "healthy",
        "service": "AI Tutor for GitHub Repositories",
        "message": "🚀 Backend is running smoothly!"
    }

