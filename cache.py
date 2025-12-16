import asyncio
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

class ScheduleCache:
    def __init__(self, max_size: int = 100, ttl_minutes: int = 5):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        self.ttl = timedelta(minutes=ttl_minutes)
        
    def _make_key(self, city: str, street: str, house: str, url: str, next_day: bool = False) -> str:
        key_data = f"{city}|{street}|{house}|{url}|{next_day}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        return datetime.now() - entry['timestamp'] > self.ttl
    
    def _cleanup_expired(self):
        expired_keys = [
            key for key, entry in self.cache.items() 
            if self._is_expired(entry)
        ]
        for key in expired_keys:
            del self.cache[key]
    
    def _evict_if_needed(self):
        if len(self.cache) >= self.max_size:
            oldest_key = min(
                self.cache.keys(), 
                key=lambda k: self.cache[k]['timestamp']
            )
            del self.cache[oldest_key]
    
    def get(self, city: str, street: str, house: str, url: str, next_day: bool = False) -> Optional[List[Dict[str, str]]]:
        key = self._make_key(city, street, house, url, next_day)
        
        if key not in self.cache:
            return None
            
        entry = self.cache[key]
        if self._is_expired(entry):
            del self.cache[key]
            return None
            
        return entry['schedule']
    
    def set(self, city: str, street: str, house: str, url: str, schedule: List[Dict[str, str]], next_day: bool = False):
        key = self._make_key(city, street, house, url, next_day)
        
        self._cleanup_expired()
        self._evict_if_needed()
        
        self.cache[key] = {
            'schedule': schedule,
            'timestamp': datetime.now()
        }
    
    def clear(self):
        self.cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        self._cleanup_expired()
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'ttl_minutes': self.ttl.total_seconds() / 60
        }

schedule_cache = ScheduleCache()
