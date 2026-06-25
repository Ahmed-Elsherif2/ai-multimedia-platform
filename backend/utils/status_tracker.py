"""
Status Tracker - Tracks processing status of files.
Uses file_manager for persistence.
"""
from datetime import datetime
from .file_manager import file_manager


class StatusTracker:
    """Track processing status of files"""
    
    def __init__(self):
        self.file_manager = file_manager
    
    def set_status(self, file_id: str, status: str, data: dict = None):
        """Set processing status for a file"""
        status_data = {
            "file_id": file_id,
            "status": status,
            "updated_at": datetime.now().isoformat(),
            "data": data or {}
        }
        self.file_manager.save_status(file_id, status_data)
    
    def get_status(self, file_id: str) -> dict:
        """Get processing status for a file"""
        return self.file_manager.get_status(file_id)
    
    def delete_status(self, file_id: str):
        """Delete status for a file"""
        self.file_manager.delete_status(file_id)
    
    def is_processed(self, file_id: str) -> bool:
        """Check if file is processed"""
        status = self.get_status(file_id)
        return status.get('status') == 'done'
    
    def is_processing(self, file_id: str) -> bool:
        """Check if file is currently processing"""
        status = self.get_status(file_id)
        return status.get('status') == 'processing'
    
    def is_failed(self, file_id: str) -> bool:
        """Check if file processing failed"""
        status = self.get_status(file_id)
        return status.get('status') == 'failed'

# Global instance
status_tracker = StatusTracker()