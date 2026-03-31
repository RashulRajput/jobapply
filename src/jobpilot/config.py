from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def _resolve_path(value: str, project_root: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((project_root / path).resolve())


def load_config(config_path: str | Path) -> Dict[str, Any]:
    config_file = Path(config_path).resolve()
    project_root = config_file.parent.parent
    data = json.loads(config_file.read_text(encoding="utf-8"))

    data["config_path"] = str(config_file)
    data["project_root"] = str(project_root)

    if data.get("resume_path"):
        data["resume_path"] = _resolve_path(data["resume_path"], project_root)

    application = data.setdefault("application", {})
    application["persisted_browser_dir"] = _resolve_path(
        application.get("persisted_browser_dir", "data/browser-profile"),
        project_root,
    )
    if application.get("resume_upload_path"):
        application["resume_upload_path"] = _resolve_path(
            application["resume_upload_path"],
            project_root,
        )

    return data


def save_json(path: str | Path, payload: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_json(path: str | Path, default: Any) -> Any:
    input_path = Path(path)
    if not input_path.exists():
        return default
    return json.loads(input_path.read_text(encoding="utf-8"))


def utc_timestamp() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
