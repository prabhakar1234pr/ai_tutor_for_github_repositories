import asyncpg
import asyncio
from app.config import settings 

async def test_connection():
    """Test database connection using async"""
    try:
        # Connect to the database
        connection = await asyncpg.connect(
            user=settings.db_user,
            password=settings.db_password,
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name
        )
        print("Connection successful!")
        
        # Example query
        result = await connection.fetchval("SELECT NOW();")
        print("Current Time:", result)

        # Close the connection
        await connection.close()
        print("Connection closed.")

    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())

