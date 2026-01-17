"""
Diagnostic script to test Azure OpenAI endpoint connectivity.
This helps identify connection issues.
"""

import asyncio

# Fix Windows encoding issues
import io
import logging
import sys
from pathlib import Path

from app.config import settings

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def test_azure_openai_connection():
    """Test Azure OpenAI endpoint connectivity."""
    print("=" * 70)
    print("🔍 Azure OpenAI Connection Diagnostic")
    print("=" * 70)
    print()

    # Check configuration
    print("📋 Configuration Check:")
    print(f"   Endpoint: {settings.azure_openai_endpoint or '❌ NOT SET'}")
    print(f"   API Key: {'✅ SET' if settings.azure_openai_key else '❌ NOT SET'}")
    print(f"   Deployment: {settings.azure_openai_deployment_gpt_4_1 or '❌ NOT SET'}")
    print(f"   API Version: {settings.azure_openai_api_version}")
    print()

    if not settings.azure_openai_endpoint:
        print("❌ ERROR: AZURE_OPENAI_ENDPOINT is not set in .env file")
        return False

    if not settings.azure_openai_key:
        print("❌ ERROR: AZURE_OPENAI_KEY is not set in .env file")
        return False

    # Test DNS resolution
    print("🌐 DNS Resolution Test:")
    import socket

    try:
        endpoint_host = (
            settings.azure_openai_endpoint.replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
        )
        ip_address = socket.gethostbyname(endpoint_host)
        print(f"   ✅ DNS Resolution: {endpoint_host} → {ip_address}")
    except socket.gaierror as e:
        print(f"   ❌ DNS Resolution FAILED: {e}")
        print(f"   💡 The endpoint '{endpoint_host}' cannot be resolved.")
        print("   💡 Possible causes:")
        print("      1. The resource name is incorrect")
        print("      2. The Azure OpenAI resource doesn't exist")
        print("      3. Network/DNS issues")
        print()
        print("   📝 Expected format: https://<resource-name>.openai.azure.com")
        print("   📝 Check your Azure Portal for the correct endpoint URL")
        return False
    except Exception as e:
        print(f"   ❌ DNS Resolution ERROR: {e}")
        return False

    print()

    # Test HTTP connectivity
    print("🔌 HTTP Connectivity Test:")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(settings.azure_openai_endpoint.rstrip("/"))
            print(f"   ✅ HTTP Connection: Status {response.status_code}")
            if response.status_code == 404:
                print("   ⚠️  Endpoint exists but path not found (this is normal for Azure OpenAI)")
            elif response.status_code == 401:
                print("   ⚠️  Authentication required (this is normal)")
    except httpx.ConnectError as e:
        print(f"   ❌ Connection FAILED: {e}")
        print("   💡 Cannot connect to the endpoint. Check firewall/proxy settings.")
        return False
    except httpx.TimeoutException:
        print("   ❌ Connection TIMEOUT: Endpoint not responding")
        return False
    except Exception as e:
        print(f"   ❌ Connection ERROR: {e}")
        return False

    print()

    # Test Pydantic AI connection
    print("🤖 Pydantic AI Connection Test:")
    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.azure import AzureProvider

        provider = AzureProvider(
            azure_endpoint=settings.azure_openai_endpoint.rstrip("/"),
            api_version=settings.azure_openai_api_version,
            api_key=settings.azure_openai_key,
        )
        model = OpenAIChatModel(settings.azure_openai_deployment_gpt_4_1, provider=provider)
        agent = Agent(model, system_prompt="You are a helpful assistant.")

        print("   Testing API call...")
        result = await agent.run("Say 'Hello' in one word.")
        print("   ✅ Pydantic AI Connection: SUCCESS")
        print(f"   ✅ Response: {result.output}")
        return True

    except Exception as e:
        print(f"   ❌ Pydantic AI Connection FAILED: {e}")
        print(f"   💡 Error details: {type(e).__name__}")
        if "getaddrinfo" in str(e) or "Connection error" in str(e):
            print("   💡 This is a DNS/network connectivity issue")
        elif "401" in str(e) or "authentication" in str(e).lower():
            print("   💡 This is an authentication issue - check your API key")
        elif "404" in str(e) or "not found" in str(e).lower():
            print("   💡 The deployment name might be incorrect")
        return False

    finally:
        print()
        print("=" * 70)


if __name__ == "__main__":
    try:
        result = asyncio.run(test_azure_openai_connection())
        if result:
            print("✅ All tests passed! Azure OpenAI is configured correctly.")
            sys.exit(0)
        else:
            print("❌ Tests failed. Please fix the issues above.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
