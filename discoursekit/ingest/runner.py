"""Ingest runner - orchestrates adapter execution and DB recording."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from discoursekit.core.db import get_connection, insert_article, insert_ingest_run, update_ingest_run
from discoursekit.ingest.base import BaseAdapter, IngestParams


def run_ingest(adapter: BaseAdapter, params: IngestParams, db_path: Path) -> str:
    """Execute an ingest run and write articles into the project DB."""
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)

    with conn:
        insert_ingest_run(
            conn,
            {
                "run_id": run_id,
                "project_id": params.project_id,
                "source": params.source,
                "params_json": json.dumps(params.to_json_dict(), ensure_ascii=False),
                "started_at": started_at,
                "status": "running",
            },
        )

    raw_count = 0
    in_range_count = 0
    error_msg = None
    status = "success"

    try:
        for article in adapter.ingest(params):
            raw_count += 1
            with conn:
                insert_article(conn, article.to_db_row(), ingest_run_id=run_id)
            in_range_count += 1
    except Exception as exc:
        status = "failed"
        error_msg = str(exc)
    finally:
        with conn:
            update_ingest_run(
                conn,
                run_id,
                {
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": status,
                    "raw_count": raw_count,
                    "in_range_count": in_range_count,
                    "error": error_msg,
                },
            )
        conn.close()

    return run_id
