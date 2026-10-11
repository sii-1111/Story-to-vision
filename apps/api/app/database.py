"""SQLite persistence for creator projects, episodes, character profiles, and generation jobs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import get_settings


def _connect() -> sqlite3.Connection:
    path = Path(get_settings().database_path).expanduser()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def initialize_database() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                story TEXT NOT NULL,
                genre TEXT NOT NULL,
                visual_style TEXT NOT NULL,
                language TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                episode_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                screenplay_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, episode_number)
            );
            CREATE TABLE IF NOT EXISTS character_profiles (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                character_id TEXT NOT NULL,
                name TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, character_id)
            );
            CREATE TABLE IF NOT EXISTS generation_jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                episode_id TEXT REFERENCES episodes(id) ON DELETE SET NULL,
                scene_number INTEGER NOT NULL,
                provider_job_id TEXT NOT NULL,
                status TEXT NOT NULL,
                video_url TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, provider_job_id)
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_project
                ON episodes(project_id, episode_number);
            CREATE INDEX IF NOT EXISTS idx_jobs_project
                ON generation_jobs(project_id, created_at);
            """
        )


def _project_row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def list_projects() -> list[dict[str, Any]]:
    initialize_database()
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.title, p.story, p.genre, p.visual_style, p.language,
                   p.created_at, p.updated_at, COUNT(DISTINCT e.id) AS episode_count,
                   COUNT(DISTINCT c.character_id) AS character_count
            FROM projects p
            LEFT JOIN episodes e ON e.project_id = p.id
            LEFT JOIN character_profiles c ON c.project_id = p.id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
        return [_project_row(row) for row in rows]


def save_project(
    title: str,
    story: str,
    screenplay: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    initialize_database()
    timestamp = now_iso()
    with connection() as conn:
        if project_id:
            exists = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not exists:
                raise KeyError("Project not found.")
            conn.execute(
                "UPDATE projects SET title=?, story=?, updated_at=? WHERE id=?",
                (title, story, timestamp, project_id),
            )
        else:
            project_id = uuid4().hex
            metadata = screenplay or {}
            conn.execute(
                """INSERT INTO projects
                (id,title,story,genre,visual_style,language,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (
                    project_id, title, story, metadata.get("genre", "romance"),
                    metadata.get("visual_style", "cinematic realism"),
                    metadata.get("language", "English"), timestamp, timestamp,
                ),
            )
        episode_id = None
        if screenplay:
            latest = conn.execute(
                "SELECT id, episode_number FROM episodes WHERE project_id=? "
                "ORDER BY episode_number DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            if latest:
                episode_id = latest["id"]
                conn.execute(
                    "UPDATE episodes SET title=?, screenplay_json=?, updated_at=? WHERE id=?",
                    (
                        screenplay.get("title", title),
                        json.dumps(screenplay, ensure_ascii=False),
                        timestamp,
                        episode_id,
                    ),
                )
            else:
                episode_number = 1
                episode_id = uuid4().hex
                conn.execute(
                    """INSERT INTO episodes
                    (id,project_id,episode_number,title,screenplay_json,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?)""",
                    (
                        episode_id, project_id, episode_number, screenplay.get("title", title),
                        json.dumps(screenplay, ensure_ascii=False), timestamp, timestamp,
                    ),
                )
            for character in screenplay.get("characters", []):
                character_id = character["id"]
                conn.execute(
                    """INSERT INTO character_profiles
                    (project_id,character_id,name,profile_json,updated_at)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(project_id,character_id) DO UPDATE SET
                    name=excluded.name, profile_json=excluded.profile_json,
                    updated_at=excluded.updated_at""",
                    (
                        project_id, character_id, character["name"],
                        json.dumps(character, ensure_ascii=False), timestamp,
                    ),
                )
            conn.execute(
                "UPDATE projects SET genre=?, visual_style=?, language=?, updated_at=? WHERE id=?",
                (
                    screenplay.get("genre", "romance"),
                    screenplay.get("visual_style", "cinematic realism"),
                    screenplay.get("language", "English"), timestamp, project_id,
                ),
            )
        return get_project(project_id, conn=conn, episode_id=episode_id)


def get_project(
    project_id: str,
    *,
    conn: sqlite3.Connection | None = None,
    episode_id: str | None = None,
) -> dict[str, Any]:
    if conn is None:
        initialize_database()
        with connection() as owned:
            return get_project(project_id, conn=owned, episode_id=episode_id)
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise KeyError("Project not found.")
    result = _project_row(row)
    result["episode_count"] = conn.execute(
        "SELECT COUNT(*) FROM episodes WHERE project_id=?", (project_id,)
    ).fetchone()[0]
    result["character_count"] = conn.execute(
        "SELECT COUNT(*) FROM character_profiles WHERE project_id=?", (project_id,)
    ).fetchone()[0]
    episodes = conn.execute(
        "SELECT * FROM episodes WHERE project_id=? ORDER BY episode_number DESC",
        (project_id,),
    ).fetchall()
    result["episodes"] = [
        {
            "id": item["id"],
            "episode_number": item["episode_number"],
            "title": item["title"],
            "screenplay": json.loads(item["screenplay_json"]),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }
        for item in episodes
    ]
    result["characters"] = [
        {**json.loads(item["profile_json"]), "updated_at": item["updated_at"]}
        for item in conn.execute(
            "SELECT * FROM character_profiles WHERE project_id=? ORDER BY name",
            (project_id,),
        ).fetchall()
    ]
    result["generation_jobs"] = [
        _project_row(item)
        for item in conn.execute(
            "SELECT * FROM generation_jobs WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    ]
    if episode_id:
        result["saved_episode_id"] = episode_id
    return result


def record_generation_job(
    project_id: str,
    scene_number: int,
    provider_job: dict[str, Any],
) -> None:
    initialize_database()
    timestamp = now_iso()
    with connection() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise KeyError("Project not found.")
        conn.execute(
            """INSERT INTO generation_jobs
            (id,project_id,scene_number,provider_job_id,status,video_url,error,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(project_id,provider_job_id) DO UPDATE SET
            status=excluded.status, video_url=excluded.video_url, error=excluded.error,
            updated_at=excluded.updated_at""",
            (
                uuid4().hex, project_id, scene_number, provider_job["job_id"],
                provider_job["status"], provider_job.get("video_url"),
                provider_job.get("error"), timestamp, timestamp,
            ),
        )


def update_generation_job(project_id: str, provider_job: dict[str, Any]) -> None:
    initialize_database()
    with connection() as conn:
        conn.execute(
            """UPDATE generation_jobs SET status=?, video_url=?, error=?, updated_at=?
            WHERE project_id=? AND provider_job_id=?""",
            (
                provider_job["status"], provider_job.get("video_url"),
                provider_job.get("error"), now_iso(), project_id, provider_job["job_id"],
            ),
        )
