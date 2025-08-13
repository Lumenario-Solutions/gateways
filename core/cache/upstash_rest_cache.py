import json
import requests
from django.core.cache.backends.base import BaseCache, DEFAULT_TIMEOUT
from django.conf import settings

class UpstashRestCache(BaseCache):
    def __init__(self, location, params):
        super().__init__(params)
        self.base_url = settings.UPSTASH_REDIS_REST_URL.rstrip("/")
        self.token = settings.UPSTASH_REDIS_REST_TOKEN

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return self.set(key, value, timeout, version)

    def get(self, key, default=None, version=None):
        try:
            resp = requests.get(
                f"{self.base_url}/get/{key}",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result")
            return default
        except Exception:
            return default

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        try:
            resp = requests.post(
                f"{self.base_url}/set/{key}/{value}",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            return resp.status_code == 200
        except Exception:
            return False

    def delete(self, key, version=None):
        try:
            resp = requests.post(
                f"{self.base_url}/del/{key}",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            return resp.status_code == 200
        except Exception:
            return False
