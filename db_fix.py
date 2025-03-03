import os
import sqlite3
import logging

class DatabaseConnection:
    def __init__(self, db_path=None):
        # Always prefer a local path for Render deployment
        if db_path and '/var/data' in db_path:
            logging.warning(f"Replacing {db_path} with local path due to Render free tier limitations")
            self.db_path = 'survey.db'
        else:
            self.db_path = db_path or 'survey.db'
        
        self.conn = None
    
    def __enter__(self):
        try:
            logging.info(f"Attempting to connect to database at {self.db_path}")
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            return self.conn
        except sqlite3.OperationalError as e:
            # If we can't access the specified path, fall back to a local DB
            logging.warning(f"Could not open database at {self.db_path}, falling back to local path")
            self.db_path = 'survey.db'
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            return self.conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is not None:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()
