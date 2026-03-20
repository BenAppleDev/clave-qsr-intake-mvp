from __future__ import annotations

import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List
from zoneinfo import ZoneInfo

from qsr_intake.connectors.base import RawEnvelope
from qsr_intake.utils import stable_hash, utc_now_iso


UploadFn = Callable[[RawEnvelope], None]


@dataclass(frozen=True)
class LocalFileSpec:
    source_entity_type: str
    file_glob: str
    parser_profile: str | None = None


@dataclass(frozen=True)
class DiscoveredFile:
    path: Path
    relative_path: str
    source_entity_type: str
    parser_profile: str | None
    observed_at: str
    partition_day: str
    content_type: str
    fingerprint: str


class LocalBridge:
    connector_name = "local_file_bridge"
    connector_version = "0.1.0"

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        params = config.get("params", {})
        self.watch_dir = Path(params["watched_directory"])
        self.checkpoint_path = Path(params["checkpoint_path"])
        self.file_specs = [LocalFileSpec(**spec) for spec in params.get("file_specs", [])]
        self.polling_interval_seconds = float(params.get("polling_interval_seconds", 5))
        self.backfill_chunk_size = int(params.get("backfill_chunk_size", 1))
        self.backfill_chunk_by = params.get("backfill_chunk_by", "file")
        self.throttle_seconds = float(params.get("throttle_seconds", 0))
        self.retry_backoff_seconds = float(params.get("retry_backoff_seconds", 0))
        self.max_retries = int(params.get("max_retries", 2))
        self.timezone = ZoneInfo(params.get("timezone", "UTC"))
        self.max_files_per_live_scan = int(params.get("max_files_per_live_scan", 100))

    def run_backfill(self, upload_fn: UploadFn) -> Dict[str, Any]:
        files = self.discover_pending_files()
        chunks = self._chunk_files(files)
        uploaded_files: List[str] = []
        failed_files: List[str] = []
        chunk_keys: List[str] = []

        for chunk in chunks:
            if not chunk:
                continue
            chunk_keys.append(chunk[0].partition_day if self.backfill_chunk_by == "day" else chunk[0].relative_path)
            for discovered in chunk:
                if self._upload_with_retry(discovered, upload_fn):
                    uploaded_files.append(discovered.relative_path)
                else:
                    failed_files.append(discovered.relative_path)
                if self.throttle_seconds:
                    time.sleep(self.throttle_seconds)

        self._touch_checkpoint_last_scan()
        return {
            "mode": "backfill",
            "uploaded_files": uploaded_files,
            "failed_files": failed_files,
            "chunks_processed": len(chunks),
            "chunk_keys": chunk_keys,
            "window": self._window_for(uploaded_files),
        }

    def run_live_iteration(self, upload_fn: UploadFn) -> Dict[str, Any]:
        files = self.discover_pending_files()[: self.max_files_per_live_scan]
        uploaded_files: List[str] = []
        failed_files: List[str] = []
        for discovered in files:
            if self._upload_with_retry(discovered, upload_fn):
                uploaded_files.append(discovered.relative_path)
            else:
                failed_files.append(discovered.relative_path)
            if self.throttle_seconds:
                time.sleep(self.throttle_seconds)

        self._touch_checkpoint_last_scan()
        return {
            "mode": "live",
            "uploaded_files": uploaded_files,
            "failed_files": failed_files,
            "chunks_processed": 1 if files else 0,
            "chunk_keys": [file.relative_path for file in files],
            "window": self._window_for(uploaded_files),
        }

    def run_live(self, upload_fn: UploadFn, iterations: int = 1) -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        for index in range(iterations):
            runs.append(self.run_live_iteration(upload_fn))
            if index < iterations - 1 and self.polling_interval_seconds:
                time.sleep(self.polling_interval_seconds)
        return runs

    def discover_pending_files(self) -> List[DiscoveredFile]:
        checkpoint = self._load_checkpoint()
        discovered: "OrderedDict[str, DiscoveredFile]" = OrderedDict()
        for spec in self.file_specs:
            for path in sorted(self.watch_dir.glob(spec.file_glob)):
                if not path.is_file():
                    continue
                relative_path = str(path.relative_to(self.watch_dir))
                fingerprint = self._fingerprint_for(path, relative_path)
                if checkpoint["processed"].get(relative_path, {}).get("fingerprint") == fingerprint:
                    continue
                observed_at = self._observed_at(path)
                discovered[relative_path] = DiscoveredFile(
                    path=path,
                    relative_path=relative_path,
                    source_entity_type=spec.source_entity_type,
                    parser_profile=spec.parser_profile,
                    observed_at=observed_at,
                    partition_day=self._partition_day(path, observed_at),
                    content_type=self._content_type_for(path),
                    fingerprint=fingerprint,
                )
        return sorted(discovered.values(), key=lambda item: (item.partition_day, item.relative_path))

    def heartbeat(self) -> Dict[str, Any]:
        pending = len(self.discover_pending_files())
        checkpoint = self._load_checkpoint()
        return {
            "ok": True,
            "connector_name": self.connector_name,
            "source_mode": self.config.get("source_mode", "local_bridge_fallback"),
            "pending_files": pending,
            "processed_files": len(checkpoint["processed"]),
            "checkpoint_path": str(self.checkpoint_path),
            "watch_dir": str(self.watch_dir),
        }

    def build_envelope(self, discovered: DiscoveredFile) -> RawEnvelope:
        return RawEnvelope(
            batch_id=self.config["batch_id"],
            customer_id=self.config["customer_id"],
            source_system=self.config["source_system"],
            source_family=self.config["source_family"],
            source_mode=self.config.get("source_mode", "local_bridge_fallback"),
            source_entity_type=discovered.source_entity_type,
            source_location_id=self.config.get("source_location_id"),
            source_object_id=discovered.relative_path,
            source_object_observed_at=discovered.observed_at,
            extracted_at=utc_now_iso(),
            content_type=discovered.content_type,
            connector_name=self.connector_name,
            connector_version=self.connector_version,
            config_version=str(self.config["version"]),
            fingerprint=discovered.fingerprint,
            payload_bytes=discovered.path.read_bytes(),
        )

    def _chunk_files(self, files: List[DiscoveredFile]) -> List[List[DiscoveredFile]]:
        if not files:
            return []
        if self.backfill_chunk_by == "day":
            grouped: "OrderedDict[str, List[DiscoveredFile]]" = OrderedDict()
            for discovered in files:
                grouped.setdefault(discovered.partition_day, []).append(discovered)
            days = list(grouped)
            chunks: List[List[DiscoveredFile]] = []
            for idx in range(0, len(days), self.backfill_chunk_size):
                chunk_days = days[idx : idx + self.backfill_chunk_size]
                chunk: List[DiscoveredFile] = []
                for day in chunk_days:
                    chunk.extend(grouped[day])
                chunks.append(chunk)
            return chunks
        return [files[idx : idx + self.backfill_chunk_size] for idx in range(0, len(files), self.backfill_chunk_size)]

    def _upload_with_retry(self, discovered: DiscoveredFile, upload_fn: UploadFn) -> bool:
        attempts = 0
        last_error: str | None = None
        while attempts <= self.max_retries:
            try:
                upload_fn(self.build_envelope(discovered))
                self._mark_processed(discovered)
                return True
            except Exception as exc:  # pragma: no cover - exercised by tests
                attempts += 1
                last_error = str(exc)
                self._record_attempt(discovered, attempts, last_error)
                if attempts > self.max_retries:
                    break
                if self.retry_backoff_seconds:
                    time.sleep(self.retry_backoff_seconds)
        self._record_failure(discovered, last_error or "upload_failed")
        return False

    def _window_for(self, uploaded_files: List[str]) -> Dict[str, str | None]:
        checkpoint = self._load_checkpoint()
        observed = [
            checkpoint["processed"][path]["observed_at"]
            for path in uploaded_files
            if path in checkpoint["processed"]
        ]
        if not observed:
            return {"window_start": None, "window_end": None}
        return {"window_start": min(observed), "window_end": max(observed)}

    def _fingerprint_for(self, path: Path, relative_path: str) -> str:
        stat = path.stat()
        return stable_hash([relative_path, stat.st_size, stat.st_mtime_ns])

    def _observed_at(self, path: Path) -> str:
        date_token = self._date_token(path)
        if date_token:
            return datetime.fromisoformat(f"{date_token}T00:00:00").replace(tzinfo=self.timezone).isoformat()
        observed = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(self.timezone)
        return observed.isoformat()

    def _partition_day(self, path: Path, observed_at: str) -> str:
        date_token = self._date_token(path)
        if date_token:
            return date_token
        return observed_at[:10]

    def _date_token(self, path: Path) -> str | None:
        for token in path.stem.split("_"):
            if len(token) == 10 and token[4] == "-" and token[7] == "-":
                return token
        return None

    def _content_type_for(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return "application/json"
        if suffix == ".csv":
            return "text/csv"
        return "application/octet-stream"

    def _load_checkpoint(self) -> Dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {"processed": {}, "attempts": {}, "failures": {}, "last_scan_at": None}
        return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))

    def _save_checkpoint(self, checkpoint: Dict[str, Any]) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")

    def _mark_processed(self, discovered: DiscoveredFile) -> None:
        checkpoint = self._load_checkpoint()
        checkpoint["processed"][discovered.relative_path] = {
            "fingerprint": discovered.fingerprint,
            "observed_at": discovered.observed_at,
            "source_entity_type": discovered.source_entity_type,
            "completed_at": utc_now_iso(),
        }
        checkpoint["failures"].pop(discovered.relative_path, None)
        checkpoint["attempts"].pop(discovered.relative_path, None)
        self._save_checkpoint(checkpoint)

    def _record_attempt(self, discovered: DiscoveredFile, attempts: int, error: str) -> None:
        checkpoint = self._load_checkpoint()
        checkpoint["attempts"][discovered.relative_path] = {
            "count": attempts,
            "last_error": error,
            "updated_at": utc_now_iso(),
        }
        self._save_checkpoint(checkpoint)

    def _record_failure(self, discovered: DiscoveredFile, error: str) -> None:
        checkpoint = self._load_checkpoint()
        checkpoint["failures"][discovered.relative_path] = {
            "error": error,
            "updated_at": utc_now_iso(),
        }
        self._save_checkpoint(checkpoint)

    def _touch_checkpoint_last_scan(self) -> None:
        checkpoint = self._load_checkpoint()
        checkpoint["last_scan_at"] = utc_now_iso()
        self._save_checkpoint(checkpoint)
