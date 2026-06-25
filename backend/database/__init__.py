"""
Database module for AI Multimedia Platform
"""
from .db import get_db, init_db, close_db, get_db_path
from . import queries

__all__ = [
    "get_db",
    "init_db", 
    "close_db",
    "get_db_path",
    "queries"
]