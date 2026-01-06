
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from app.services.rag.indexer import CodeIndexer, IndexUpdateMode

class TestIndexerLogic(unittest.IsolatedAsyncioTestCase):
    async def test_smart_index_mode_selection(self):
        # Mock dependencies
        mock_vector_store = MagicMock()
        mock_embedding_service = MagicMock()
        
        indexer = CodeIndexer(
            collection_name="test_collection",
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store
        )
        
        # 1. Test: New collection (should be FULL)
        mock_vector_store.is_new_collection = True
        mock_vector_store.initialize = AsyncMock()
        mock_vector_store.get_embedding_config = MagicMock(return_value={})
        mock_vector_store.get_collection_metadata = MagicMock(return_value={})
        
        # We need to mock _check_rebuild_needed indirectly or just let it run
        # Since is_new_collection is True, _check_rebuild_needed returns (False, "")
        
        # We'll use a wrapper to capture the calls to _full_index and _incremental_index
        indexer._full_index = AsyncMock()
        indexer._incremental_index = AsyncMock()
        
        # Mock _full_index as an async generator
        async def mock_gen(*args, **kwargs):
            yield MagicMock()
        indexer._full_index.side_effect = mock_gen
        indexer._incremental_index.side_effect = mock_gen

        # Run smart_index_directory
        async for _ in indexer.smart_index_directory(directory="/tmp/test"):
            pass
            
        # Verify FULL mode was selected because it's a new collection
        indexer._full_index.assert_called_once()
        indexer._incremental_index.assert_not_called()
        
        # 2. Test: Existing collection, no rebuild needed (should be INCREMENTAL)
        indexer._full_index.reset_mock()
        indexer._incremental_index.reset_mock()
        mock_vector_store.is_new_collection = False
        
        async for _ in indexer.smart_index_directory(directory="/tmp/test"):
            pass
            
        indexer._full_index.assert_not_called()
        indexer._incremental_index.assert_called_once()

if __name__ == "__main__":
    unittest.main()
