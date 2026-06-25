"""
File Manager - Centralized file operations for uploads, storage, and cleanup.
"""
import os
import json
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename

from config.settings import settings


class FileManager:
    """Centralized file management for uploads and results"""
    
    def __init__(self):
        # Use settings for directories
        self.upload_dir = settings.UPLOAD_FOLDER
        self.results_dir = settings.RESULTS_FOLDER
        self.status_dir = settings.STATUS_FOLDER
        self.data_dir = settings.DATA_DIR
        
        # Ensure directories exist
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.status_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"[FileManager] Upload: {self.upload_dir}")
        print(f"[FileManager] Results: {self.results_dir}")
        print(f"[FileManager] Status: {self.status_dir}")
    
    def save_upload(self, file) -> dict:
        """
        Save an uploaded file.
        
        Returns:
            dict: {file_id, filename, path, size, type}
        """
        file_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        save_path = self.upload_dir / f"{file_id}_{filename}"
        
        file.save(str(save_path))
        
        return {
            "file_id": file_id,
            "filename": filename,
            "path": str(save_path),
            "size": save_path.stat().st_size,
            "type": self._get_file_type(filename),
            "uploaded_at": datetime.now().isoformat()
        }
    
    def get_upload_path(self, file_id: str):
        """Get the path of an uploaded file by ID"""
        matches = list(self.upload_dir.glob(f"{file_id}_*"))
        if matches:
            return matches[0]
        return None
    
    def save_result(self, file_id: str, data: dict):
        """Save processing results"""
        file_path = self.results_dir / f"{file_id}.json"
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return str(file_path)
    
    def get_result(self, file_id: str) -> dict:
        """Get processing results"""
        file_path = self.results_dir / f"{file_id}.json"
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        return None
    
    def save_status(self, file_id: str, status: dict):
        """Save processing status"""
        file_path = self.status_dir / f"{file_id}.json"
        with open(file_path, 'w') as f:
            json.dump(status, f, indent=2)
    
    def get_status(self, file_id: str) -> dict:
        """Get processing status"""
        file_path = self.status_dir / f"{file_id}.json"
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        return {"status": "not_found"}
    
    def delete_status(self, file_id: str):
        """Delete status file"""
        file_path = self.status_dir / f"{file_id}.json"
        if file_path.exists():
            file_path.unlink()
    
    def delete_result(self, file_id: str):
        """Delete result file"""
        file_path = self.results_dir / f"{file_id}.json"
        if file_path.exists():
            file_path.unlink()
    
    def cleanup_file(self, file_id: str, keep_results: bool = True):
        """
        Delete uploaded file and optionally results/status.
        """
        deleted = []
        
        # Delete uploaded file
        upload = self.get_upload_path(file_id)
        if upload and upload.exists():
            size = upload.stat().st_size / 1024 / 1024
            upload.unlink()
            deleted.append(f"Upload: {upload.name} ({size:.2f}MB)")
        
        # Delete status
        self.delete_status(file_id)
        deleted.append("Status")
        
        # Optionally delete results
        if not keep_results:
            self.delete_result(file_id)
            deleted.append("Results")
        
        return deleted
    
    def _get_file_type(self, filename: str) -> str:
        """Determine file type from extension"""
        ext = filename.lower().split('.')[-1]
        audio_extensions = ['mp3', 'wav', 'm4a', 'flac', 'aac', 'ogg', 'wma']
        video_extensions = ['mp4', 'avi', 'mov', 'mkv', 'webm']
        
        if ext in audio_extensions:
            return 'audio'
        elif ext in video_extensions:
            return 'video'
        elif ext == 'pdf':
            return 'pdf'
        else:
            return 'unknown'

# Global instance
file_manager = FileManager()