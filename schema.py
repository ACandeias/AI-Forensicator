"""AIFT data models: AIArtifact and CollectionRun dataclasses."""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class AIArtifact:
    """A single forensic artifact from an AI tool."""
    source_tool: str
    artifact_type: str
    id: str = field(default_factory=_new_uuid)
    timestamp: Optional[str] = None
    file_path: Optional[str] = None
    file_hash_sha256: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_modified: Optional[str] = None
    file_created: Optional[str] = None
    user: Optional[str] = None
    hostname: Optional[str] = None
    content_preview: Optional[str] = None
    raw_data: Optional[str] = None
    model_identified: Optional[str] = None
    conversation_id: Optional[str] = None
    message_role: Optional[str] = None
    token_estimate: Optional[int] = None
    metadata: Optional[str] = None  # JSON string
    collection_timestamp: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CollectionRun:
    """Metadata about a single collection run."""
    id: str = field(default_factory=_new_uuid)
    start_time: str = field(default_factory=_utc_now_iso)
    end_time: Optional[str] = None
    collectors_run: Optional[str] = None  # JSON list of names
    total_artifacts: int = 0
    errors: Optional[str] = None  # JSON list of error strings
    hostname: Optional[str] = None
    username: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
