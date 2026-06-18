import hashlib
import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from threading import Lock


def sha256_text(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def split_api_keys(primary_key="", key_list=""):
    keys = [item.strip() for item in (key_list or "").replace("\n", ",").split(",") if item.strip()]
    primary_key = (primary_key or "").strip()
    if primary_key and primary_key not in keys:
        keys.insert(0, primary_key)
    return keys


class ApiKeyRing:
    def __init__(self, keys):
        self.keys = list(keys or [])
        self.index = 0
        self.lock = Lock()

    def next(self):
        if not self.keys:
            raise RuntimeError("missing LLM API key")
        with self.lock:
            key = self.keys[self.index % len(self.keys)]
            self.index += 1
            return key


def cache_key(kind, payload, provider, model, prompt_version):
    identity = {
        "kind": kind,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "payload_hash": sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    }
    return sha256_text(json.dumps(identity, ensure_ascii=False, sort_keys=True))


@dataclass
class JsonlSummaryCache:
    path: str
    ttl_seconds: int
    enabled: bool = True
    records: dict = field(default_factory=dict)

    def load(self, now=None):
        if not self.enabled or not self.path or not os.path.exists(self.path):
            return
        now = time.time() if now is None else now
        cutoff = now - self.ttl_seconds
        with open(self.path, "r", encoding="utf-8") as cache_file:
            for line in cache_file:
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if float(record.get("created_at", 0) or 0) >= cutoff:
                    key = record.get("key")
                    if key:
                        self.records[key] = record

    def get(self, key, now=None):
        if not self.enabled:
            return None
        record = self.records.get(key)
        if not record:
            return None
        now = time.time() if now is None else now
        if float(record.get("created_at", 0) or 0) < now - self.ttl_seconds:
            return None
        return record.get("value")

    def set(self, key, kind, value, metadata=None, now=None):
        if not self.enabled or value is None:
            return
        now = time.time() if now is None else now
        record = {
            "key": key,
            "kind": kind,
            "created_at": now,
            "value": value,
        }
        if metadata:
            record.update(metadata)
        self.records[key] = record
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as cache_file:
            cache_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def chat_completion_text(
    *,
    base_url,
    api_key,
    model,
    messages,
    timeout,
    temperature=0.2,
    response_format=None,
):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]
