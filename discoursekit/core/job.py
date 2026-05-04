"""Job tracking model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Job:
    """Tracks the progress of a long-running operation."""

    job_id: str
    project_id: str
    schema_id: str
    prompt_version_id: str
    provider: str
    model: str
    temperature: float
    sample_size: int
    started_at: str
    status: str
    finished_at: Optional[str] = None
    n_processed: int = 0
    n_errors: int = 0
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    estimated_cost_usd: float = 0.0

    @classmethod
    def create(
        cls,
        job_id: str,
        project_id: str,
        schema_id: str,
        prompt_version_id: str,
        provider: str,
        model: str,
        temperature: float,
        sample_size: int,
    ) -> "Job":
        return cls(
            job_id=job_id,
            project_id=project_id,
            schema_id=schema_id,
            prompt_version_id=prompt_version_id,
            provider=provider,
            model=model,
            temperature=temperature,
            sample_size=sample_size,
            started_at=datetime.now(timezone.utc).isoformat(),
            status="running",
        )

    def mark_finished(self, status: str = "success") -> None:
        if status not in ("success", "failed", "cancelled"):
            raise ValueError(f"Invalid status: {status!r}")
        self.status = status
        self.finished_at = datetime.now(timezone.utc).isoformat()

    def to_db_row(self) -> dict:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "schema_id": self.schema_id,
            "prompt_version_id": self.prompt_version_id,
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "sample_size": self.sample_size,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "n_processed": self.n_processed,
            "n_errors": self.n_errors,
            "prompt_tokens": self.prompt_tokens,
            "candidates_tokens": self.candidates_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
        }
