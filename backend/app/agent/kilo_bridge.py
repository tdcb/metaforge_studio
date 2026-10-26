"""Headless @kilocode/cli (kilo run) Subprocess Runner & Workspace Bridge."""
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from ..config import settings


def is_kilo_cli_available() -> bool:
    """Check if the `kilo` CLI binary is installed and accessible on PATH."""
    return shutil.which(settings.kilo_cli_binary) is not None


def execute_kilo_command(
    prompt: str,
    workspace_dir: Optional[Path] = None,
    provider_model: Optional[str] = None,
    timeout_seconds: int = 45,
) -> Dict[str, Any]:
    """
    Invoke `kilo run --model <provider> "<prompt>"` headlessly inside `workspace_model/`
    where `canonical_model.json` and `exported_dbt/` reside.
    Returns structured stdout/stderr, exit code, and command trace.
    """
    target_dir = workspace_dir or settings.workspace_model_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    model_arg = provider_model or settings.kilo_default_model

    scoped_instruction = (
        f"You are operating inside the MetaForge Studio canonical workspace ({target_dir}). "
        f"The canonical metamodel is stored in canonical_model.json and dbt files are in exported_dbt/. "
        f"Task: {prompt}"
    )
    cmd = [
        settings.kilo_cli_binary,
        "run",
        "--model",
        model_arg,
        scoped_instruction,
    ]
    cmd_display = f'{settings.kilo_cli_binary} run --model {model_arg} "{prompt}"'

    if not is_kilo_cli_available():
        return {
            "executed_cli": False,
            "command": cmd_display,
            "exit_code": 127,
            "stdout": "",
            "stderr": (
                f"@kilocode/cli binary ('{settings.kilo_cli_binary}') not detected in host PATH. "
                "Automatically routed execution through MetaForge Built-in Architect Agent on workspace_model/canonical_model.json."
            ),
        }

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(target_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "executed_cli": proc.returncode == 0,
            "command": cmd_display,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:
        return {
            "executed_cli": False,
            "command": cmd_display,
            "exit_code": 1,
            "stdout": "",
            "stderr": f"kilo-cli execution error: {exc}. Falling back to Built-in Architect Agent.",
        }
