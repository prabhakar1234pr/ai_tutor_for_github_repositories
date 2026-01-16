"""
Tests for API routes (routes.py)
"""


class TestRoutes:
    """Test cases for /api routes"""

    def test_route1(self, client):
        """Test GET /api/route1"""
        response = client.get("/api/route1")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "✅ You successfully called Route 1!"
        assert data["button"] == "Button One"
        assert "data" in data

    def test_route2(self, client):
        """Test GET /api/route2"""
        response = client.get("/api/route2")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "✅ You successfully called Route 2!"
        assert data["button"] == "Button Two"
        assert "data" in data

    def test_hello(self, client):
        """Test GET /api/hello"""
        response = client.get("/api/hello")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "👋 Hello from API routes!"
        assert data["status"] == "connected"
        assert data["backend"] == "FastAPI"

    def test_health_check(self, client):
        """Test GET /api/health"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "AI Tutor for GitHub Repositories"
        assert "message" in data
