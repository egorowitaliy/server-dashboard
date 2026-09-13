from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"


class CommandError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def find_command(name: str) -> str:
    path = shutil.which(name, path=SAFE_PATH)

    if path is None:
        raise CommandError(f"Команда не найдена: {name}")

    return path


def run_command(
    args: list[str],
    *,
    timeout: float = 5.0,
) -> CommandResult:
    if not args:
        raise CommandError("Пустая команда")

    try:
        completed = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env={
                "PATH": SAFE_PATH,
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandError(
            f"Timeout при выполнении {args[0]}"
        ) from exc
    except OSError as exc:
        raise CommandError(
            f"Не удалось выполнить {args[0]}: {exc}"
        ) from exc

    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )
