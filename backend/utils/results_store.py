"""
Results Store - Persists processing results with caching.
Uses file_manager for persistence.
"""
from .file_manager import file_manager


class ResultsStore:
    """Store and retrieve processing results with in-memory cache"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.file_manager = file_manager
        self._cache = {}
    
    def save(self, file_id: str, data: dict):
        """Save results for a file"""
        self.file_manager.save_result(file_id, data)
        self._cache[file_id] = data
    
    def get(self, file_id: str) -> dict:
        """Get results for a file"""
        if file_id in self._cache:
            return self._cache[file_id]
        
        data = self.file_manager.get_result(file_id)
        if data:
            self._cache[file_id] = data
        return data
    
    def has(self, file_id: str) -> bool:
        """Check if results exist for a file"""
        if file_id in self._cache:
            return True
        return self.file_manager.get_result(file_id) is not None
    
    def delete(self, file_id: str):
        """Delete results for a file"""
        if file_id in self._cache:
            del self._cache[file_id]
        self.file_manager.delete_result(file_id)
    
    def clear(self):
        """Clear all cached results (does not delete files)"""
        self._cache.clear()

# Global instance
results_store = ResultsStore()