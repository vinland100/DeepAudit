
import sys
from unittest.mock import MagicMock, AsyncMock
import unittest

# Mock modules that might be missing or fail on import
mock_chromadb = MagicMock()
sys.modules['chromadb'] = mock_chromadb
sys.modules['chromadb.config'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['tiktoken'] = MagicMock()
sys.modules['tree_sitter'] = MagicMock()
sys.modules['tree_sitter_language_pack'] = MagicMock()

# Now import the class to test
# We need to ensure dependencies are mocked before this
from app.services.rag.indexer import CodeIndexer, IndexUpdateMode

class TestIndexerLogicIsolated(unittest.IsolatedAsyncioTestCase):
    async def test_smart_index_mode_selection(self):
        mock_vector_store = MagicMock()
        mock_embedding_service = MagicMock()
        
        indexer = CodeIndexer(
            collection_name="test_collection",
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
        
        # Mock methods that are called during smart_index_directory
        indexer.initialize = AsyncMock(return_value=(False, ""))
        indexer._full_index = AsyncMock()
        indexer._incremental_index = AsyncMock()
        
        async def mock_gen(*args, **kwargs):
            yield MagicMock()
        indexer._full_index.side_effect = mock_gen
        indexer._incremental_index.side_effect = mock_gen

        # 1. Test: New collection (should be FULL)
        mock_vector_store.is_new_collection = True
        
        async for _ in indexer.smart_index_directory(directory="/tmp/test"):
            pass
            
        # Verify FULL mode was selected because it's a new collection
        indexer._full_index.assert_called_once()
        indexer._incremental_index.assert_not_called()
        
        # 2. Test: Existing collection, no rebuild needed (should be INCREMENTAL)
        indexer._full_index.reset_mock()
        indexer._incremental_index.reset_mock()
        mock_vector_store.is_new_collection = False
        indexer.initialize = AsyncMock(return_value=(False, "")) # needs_rebuild = False
        
        async for _ in indexer.smart_index_directory(directory="/tmp/test"):
            pass
            
        indexer._full_index.assert_not_called()
        indexer._incremental_index.assert_called_once()

    async def test_needs_rebuild_selection(self):
        mock_vector_store = MagicMock()
        mock_embedding_service = MagicMock()
        
        indexer = CodeIndexer(
            collection_name="test_collection",
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
        
        indexer._full_index = AsyncMock()
        indexer._incremental_index = AsyncMock()
        async def mock_gen(*args, **kwargs):
            yield MagicMock()
        indexer._full_index.side_effect = mock_gen
        
        # Test: Existing collection, but needs_rebuild is True (should be FULL)
        mock_vector_store.is_new_collection = False
        indexer.initialize = AsyncMock(return_value=(True, "Config changed"))
        
        async for _ in indexer.smart_index_directory(directory="/tmp/test"):
            pass
            
        indexer._full_index.assert_called_once()

if __name__ == "__main__":
    unittest.main()
