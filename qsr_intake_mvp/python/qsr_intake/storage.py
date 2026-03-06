from __future__ import annotations

from pathlib import Path


class LocalObjectStore:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def put_bytes(self, key: str, payload: bytes) -> str:
        target = self.base_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return key

    def get_bytes(self, key: str) -> bytes:
        return (self.base_dir / key).read_bytes()
