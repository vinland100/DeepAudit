import asyncio
import sys
import os

# Add backend to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from unittest.mock import AsyncMock, patch
from app.services.scanner import get_gitea_branches

async def test_gitea_branches():
    print("Testing Gitea branch fetching with various mocked responses...")
    
    repo_url = "http://gitea.example.com/owner/repo"
    token = "test-token"
    
    test_cases = [
        {
            "name": "Normal list response",
            "mock_response": [{"name": "main"}, {"name": "develop"}],
            "expected_count": 2
        },
        {
            "name": "Null (None) response",
            "mock_response": None,
            "expected_count": 0
        },
        {
            "name": "Empty list response",
            "mock_response": [],
            "expected_count": 0
        },
        {
            "name": "Dict response (unexpected)",
            "mock_response": {"message": "Not found"},
            "expected_count": 0
        },
        {
            "name": "List with invalid items",
            "mock_response": [{"name": "main"}, "invalid", {"other": "data"}],
            "expected_count": 1
        }
    ]
    
    for case in test_cases:
        print(f"\nCase: {case['name']}")
        with patch('app.services.scanner.gitea_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = case['mock_response']
            try:
                branches = await get_gitea_branches(repo_url, token)
                print(f"Result: {branches}")
                assert len(branches) == case['expected_count']
                print("✅ Pass")
            except Exception as e:
                print(f"❌ Fail with exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_gitea_branches())
