import hashlib
import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from threading import Lock


def public_payload(payload):
    return {key: value for key, value in (payload or {}).items() if not str(key).startswith("_")}


def redfox_cache_key(payload):
    identity = {
        "url": (payload or {}).get("_cache_url", ""),
        "payload": public_payload(payload),
    }
    text = json.dumps(identity, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def post_json(url, payload, api_key, timeout=90, user_agent="DailyBriefingBot/0.1"):
    data = json.dumps(public_payload(payload), ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-KEY": api_key,
            "X-API-Key": api_key,
            "User-Agent": user_agent,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class RawJsonCache:
    path: str
    max_entries: int = 120
    lock: Lock = field(default_factory=Lock)

    def load(self):
        if not self.path or not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as cache_file:
                data = json.load(cache_file)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, cache):
        if not self.path:
            return
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        trimmed = dict(list((cache or {}).items())[-self.max_entries :])
        with open(self.path, "w", encoding="utf-8") as cache_file:
            json.dump(trimmed, cache_file, ensure_ascii=False)

    def get(self, payload, *, force_refresh=False, ttl_seconds=None, now=None):
        if force_refresh:
            return None
        cache = self.load()
        record = cache.get(redfox_cache_key(payload))
        if not record:
            return None
        if ttl_seconds is not None:
            now = time.time() if now is None else now
            age = now - float(record.get("created_at", 0) or 0)
            if age > ttl_seconds:
                return None
        return record.get("data")

    def set(self, payload, data, metadata=None, now=None):
        now = time.time() if now is None else now
        with self.lock:
            cache = self.load()
            record = {
                "created_at": now,
                "data": data,
            }
            if metadata:
                record.update(metadata)
            cache[redfox_cache_key(payload)] = record
            self.save(cache)
