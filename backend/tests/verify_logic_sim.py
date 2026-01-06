
import unittest
from enum import Enum

class IndexUpdateMode(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    SMART = "smart"

def select_mode_simulation(update_mode, needs_rebuild, is_new_collection, rebuild_reason=""):
    """
    Simulates the logic in indexer.py:smart_index_directory
    """
    if update_mode == IndexUpdateMode.SMART:
        # The logic we implemented:
        if needs_rebuild or is_new_collection:
            actual_mode = IndexUpdateMode.FULL
            reason = rebuild_reason if needs_rebuild else "新集合"
            print(f"🔄 智能模式: 选择全量重建 (原因: {reason})")
            return actual_mode
        else:
            actual_mode = IndexUpdateMode.INCREMENTAL
            print("📝 智能模式: 选择增量更新")
            return actual_mode
    else:
        return update_mode

class TestSimulation(unittest.TestCase):
    def test_new_collection(self):
        # Case: Smart mode, new collection, no config change
        mode = select_mode_simulation(IndexUpdateMode.SMART, False, True)
        self.assertEqual(mode, IndexUpdateMode.FULL)

    def test_existing_rebuild(self):
        # Case: Smart mode, existing collection, config change
        mode = select_mode_simulation(IndexUpdateMode.SMART, True, False, "Model changed")
        self.assertEqual(mode, IndexUpdateMode.FULL)

    def test_existing_no_rebuild(self):
        # Case: Smart mode, existing collection, no change
        mode = select_mode_simulation(IndexUpdateMode.SMART, False, False)
        self.assertEqual(mode, IndexUpdateMode.INCREMENTAL)

if __name__ == "__main__":
    unittest.main()
