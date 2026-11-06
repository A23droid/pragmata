import asyncio
import logging
import os
import re
import shlex
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# Bounded output limit: 50 KB
MAX_OUTPUT_BYTES = 50 * 1024

# Dangerous commands and patterns blocked by security policy
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/[^\s]*",               # rm -rf /
    r":\(\)\s*\{\s*:\|:&\s*\};:",         # Fork bomb
    r"/var/run/docker\.sock",              # Docker socket mount attempt
    r"\bcurl\s+.*\|\s*(?:bash|sh|zsh)",    # Piping web downloads to shell
    r"\bwget\s+.*\|\s*(?:bash|sh|zsh)",
    r"\bmkfs\b",                           # Filesystem format
    r"\bdd\s+if=/dev/",                    # Raw disk write
    r"\bchmod\s+-R\s+777\s+/",             # Root permission wipe
    r">\s*/dev/sd[a-z]",                   # Overwriting disk partitions
    r"\bshutdown\b",
    r"\breboot\b",
]


@dataclass
class SandboxResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    error_message: Optional[str] = None


class CommandSecurityViolation(Exception):
    """Raised when an untrusted or agent-proposed command violates security policy."""
    pass


def validate_command_policy(command: str) -> None:
    """
    Validate command string against strict security policy.
    Rejects commands that attempt to escape, damage the system, or execute fork bombs.
    """
    stripped = command.strip()
    if not stripped:
        raise CommandSecurityViolation("Empty command is not permitted.")

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            logger.warning(f"Blocked dangerous command matching pattern '{pattern}': {stripped[:100]}")
            raise CommandSecurityViolation(
                f"Command rejected by security policy: matched dangerous pattern."
            )


class DockerSandbox:
    """
    Isolated, resource-bounded Docker execution sandbox.
    Runs commands in a strictly restricted container environment:
      - CPU & memory capped
      - PID limit (anti-fork bomb)
      - Network disabled by default (offline)
      - Host secrets & environment completely scrubbed
      - Strict execution timeouts with guaranteed container destruction
      - Workspace mounted with restricted access
    """

    def __init__(
        self,
        workspace_path: Path,
        image: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        network_enabled: bool = False,
        read_only_workspace: bool = False,
    ):
        self.workspace_path = workspace_path.resolve()
        self.image = image or settings.SANDBOX_DEFAULT_IMAGE
        self.timeout_seconds = timeout_seconds or settings.SANDBOX_DEFAULT_TIMEOUT
        self.network_enabled = network_enabled
        self.read_only_workspace = read_only_workspace
        self.container_id = f"pragmata_sb_{uuid.uuid4().hex[:12]}"

    async def run_command(
        self,
        command: str,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """
        Execute a controlled command inside the sandbox container.
        Enforces policy validation, resource bounds, timeouts, and cleanup.
        """
        # 1. Enforce command policy check
        validate_command_policy(command)

        # 2. Build docker run arguments with strict isolation
        mount_mode = "ro" if self.read_only_workspace else "rw"
        volume_mount = f"{self.workspace_path}:/workspace:{mount_mode}"

        docker_args = [
            "docker", "run",
            "--name", self.container_id,
            "--rm",
            # Resource constraints
            f"--cpus={settings.SANDBOX_MAX_CPU}",
            f"-m={settings.SANDBOX_MAX_MEMORY}",
            "--pids-limit=100",
            # Filesystem restrictions
            "-v", volume_mount,
            "-w", "/workspace",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            # User isolation (UID 1000)
            "--user", "1000:1000",
        ]

        # Network isolation (default: completely disconnected)
        if not self.network_enabled:
            docker_args.extend(["--network", "none"])
        else:
            docker_args.extend(["--network", "bridge"])

        # Environment variables: scrub all host environment variables!
        # Only inject explicitly provided non-sensitive variables.
        clean_container_env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": "/tmp",
            "TERM": "xterm",
            "LANG": "C.UTF-8",
        }
        if env_vars:
            for k, v in env_vars.items():
                # Prevent leaking keys or tokens
                if any(sec in k.upper() for sec in ["SECRET", "KEY", "TOKEN", "PASS", "AUTH"]):
                    logger.warning(f"Prevented passing sensitive environment variable '{k}' into sandbox.")
                    continue
                clean_container_env[k] = v

        for k, v in clean_container_env.items():
            docker_args.extend(["-e", f"{k}={v}"])

        docker_args.extend([
            self.image,
            "sh", "-c", command,
        ])

        start_time = time.monotonic()
        timed_out = False
        stdout_str = ""
        stderr_str = ""
        exit_code = -1
        error_msg = None

        logger.info(f"Sandbox container '{self.container_id}' starting command: {command[:80]}...")

        # Host environment for invoking the docker client itself (minimal)
        host_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        }
        if "DOCKER_HOST" in os.environ:
            host_env["DOCKER_HOST"] = os.environ["DOCKER_HOST"]

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=host_env,
            )

            # Wait for execution with strict bounded timeout
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(self.timeout_seconds),
            )
            exit_code = proc.returncode

            # Bounded output capture (anti-DOS)
            stdout_str = stdout_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            stderr_str = stderr_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")

        except asyncio.TimeoutError:
            timed_out = True
            error_msg = f"Execution timed out after {self.timeout_seconds} seconds."
            logger.warning(f"Sandbox container '{self.container_id}' timed out. Forcing termination.")
            await self._force_kill_container()
            exit_code = 124  # Standard timeout exit code
        except Exception as ex:
            error_msg = str(ex)
            logger.error(f"Sandbox container '{self.container_id}' execution error: {ex}")
            await self._force_kill_container()
            exit_code = 1
        finally:
            duration = time.monotonic() - start_time
            # Ensure container is destroyed
            await self._force_kill_container()

        logger.info(
            f"Sandbox '{self.container_id}' finished in {duration:.2f}s with exit_code={exit_code} (timed_out={timed_out})"
        )

        return SandboxResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_seconds=round(duration, 3),
            timed_out=timed_out,
            error_message=error_msg,
        )

    async def _force_kill_container(self) -> None:
        """Forcefully kill and remove the docker container if it is still running."""
        try:
            kill_proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", self.container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin")},
            )
            await kill_proc.wait()
        except Exception:
            pass
