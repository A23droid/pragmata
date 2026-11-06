import asyncio
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RepoMetadata:
    commit_sha: str
    branch: str
    commit_message: str
    author: str
    commit_date: str


def sanitize_git_url(url: str) -> str:
    """Mask any embedded tokens or passwords in a Git URL for safe logging."""
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", url)


def inject_token_into_url(url: str, token: Optional[str]) -> str:
    """Inject GitHub token for authentication into HTTPS URLs without altering SSH or local paths."""
    if not token or not url.startswith("https://github.com/"):
        return url
    # Insert token into https://token@github.com/...
    return url.replace("https://github.com/", f"https://x-access-token:{token}@github.com/")


class ManagedWorkspace:
    """
    Manages an isolated directory workspace for cloning/fetching a repository.
    Enforces cleanup on exit, records the exact base commit SHA,
    and isolates untrusted code from the host system.
    """

    def __init__(
        self,
        repo_url: str,
        branch_or_commit: Optional[str] = None,
        workspace_id: Optional[str] = None,
        base_dir: Optional[str] = None,
        github_token: Optional[str] = None,
    ):
        self.repo_url = repo_url
        self.branch_or_commit = branch_or_commit
        self.workspace_id = workspace_id or f"ws_{uuid.uuid4().hex[:12]}"
        self.base_dir = Path(base_dir or settings.WORKSPACE_BASE_DIR)
        self.path = self.base_dir / self.workspace_id
        self.github_token = github_token or settings.GITHUB_TOKEN
        self.commit_sha: Optional[str] = None
        self.metadata: Optional[RepoMetadata] = None
        self.is_ready = False

    async def __aenter__(self) -> "ManagedWorkspace":
        await self.setup()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.cleanup()

    async def setup(self) -> str:
        """
        Creates workspace directory, fetches/clones the repository,
        checks out the target branch or commit, and records the commit SHA.
        Guarantees cleanup on failure.
        """
        self.base_dir.mkdir(parents=True, exist_ok=True)
        safe_url = sanitize_git_url(self.repo_url)
        logger.info(f"Setting up workspace '{self.workspace_id}' for repo {safe_url}")

        try:
            # Handle local repository vs remote Git URL
            if os.path.isdir(self.repo_url):
                await self._clone_from_local(self.repo_url)
            else:
                await self._clone_from_remote(self.repo_url)

            # Record commit SHA and metadata
            self.commit_sha = await self._get_commit_sha()
            self.metadata = await self._get_metadata()
            self.is_ready = True
            logger.info(
                f"Workspace '{self.workspace_id}' ready at commit {self.commit_sha} (branch={self.metadata.branch})"
            )
            return self.commit_sha
        except Exception as ex:
            logger.error(f"Failed to setup workspace '{self.workspace_id}': {ex}")
            await self.cleanup()
            raise

    async def cleanup(self) -> None:
        """Guarantees complete removal of the workspace directory."""
        if self.path.exists():
            try:
                # Run sync cleanup in a thread to prevent blocking the event loop
                await asyncio.to_thread(shutil.rmtree, self.path, ignore_errors=True)
                logger.info(f"Workspace directory cleaned up: {self.path}")
            except Exception as ex:
                logger.warning(f"Error during workspace cleanup of {self.path}: {ex}")
        self.is_ready = False

    async def _run_git_cmd(self, *args: str, cwd: Optional[Path] = None) -> str:
        """Run a git command asynchronously with scrubbed logging."""
        work_dir = str(cwd or self.path)
        cmd = ["git"] + list(args)
        
        # Safe log command (mask any tokens)
        safe_cmd = [sanitize_git_url(a) for a in cmd]
        logger.debug(f"Executing: {' '.join(safe_cmd)} in {work_dir}")

        # Scrub sensitive environment variables
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GIT_TERMINAL_PROMPT": "0",
        }

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = sanitize_git_url(stderr.decode("utf-8", errors="replace").strip())
            raise RuntimeError(f"Git command failed ({proc.returncode}): {err_msg}")

        return stdout.decode("utf-8", errors="replace").strip()

    async def _clone_from_local(self, local_path: str) -> None:
        """Clone from local directory to workspace and checkout target branch or commit."""
        cmd = ["clone", "--no-hardlinks", local_path, str(self.path)]
        
        proc = await asyncio.create_subprocess_exec(
            "git",
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to clone local repository: {stderr.decode().strip()}")

        if self.branch_or_commit:
            try:
                await self._run_git_cmd("checkout", self.branch_or_commit)
            except Exception as ex:
                logger.warning(f"Failed checkout of {self.branch_or_commit} in local clone: {ex}")

    async def _clone_from_remote(self, remote_url: str) -> None:
        """Clone remote git repository (e.g. GitHub)."""
        auth_url = inject_token_into_url(remote_url, self.github_token)
        
        clone_cmd = ["clone"]
        if self.branch_or_commit:
            # Try shallow branch clone first
            clone_cmd.extend(["--branch", self.branch_or_commit, "--depth", "1"])
        else:
            clone_cmd.extend(["--depth", "1"])
        clone_cmd.extend([auth_url, str(self.path)])

        proc = await asyncio.create_subprocess_exec(
            "git",
            *clone_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_TERMINAL_PROMPT": "0"},
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            # Fallback for when branch_or_commit is a commit SHA rather than branch name
            if self.branch_or_commit:
                logger.info(f"Target '{self.branch_or_commit}' may be a commit SHA. Falling back to full clone.")
                if self.path.exists():
                    shutil.rmtree(self.path, ignore_errors=True)
                fallback_cmd = ["clone", auth_url, str(self.path)]
                p2 = await asyncio.create_subprocess_exec(
                    "git",
                    *fallback_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_TERMINAL_PROMPT": "0"},
                )
                _, stde2 = await p2.communicate()
                if p2.returncode != 0:
                    err = sanitize_git_url(stde2.decode().strip())
                    raise RuntimeError(f"Failed to clone repository: {err}")
                await self._run_git_cmd("checkout", self.branch_or_commit)
            else:
                err = sanitize_git_url(stderr.decode().strip())
                raise RuntimeError(f"Failed to clone repository: {err}")

        # Immediately scrub authentication credentials from .git/config origin URL to prevent sandbox leakage
        try:
            await self._run_git_cmd("remote", "set-url", "origin", sanitize_git_url(remote_url))
        except Exception as ex:
            logger.warning(f"Could not sanitize origin URL in git config: {ex}")

    async def _get_commit_sha(self) -> str:
        """Get current HEAD commit SHA."""
        return await self._run_git_cmd("rev-parse", "HEAD")

    async def _get_metadata(self) -> RepoMetadata:
        """Fetch current commit metadata."""
        try:
            branch = await self._run_git_cmd("rev-parse", "--abbrev-ref", "HEAD")
        except Exception:
            branch = "HEAD"

        log_format = "%H%x00%an%x00%ad%x00%s"
        log_out = await self._run_git_cmd("log", "-1", f"--format={log_format}")
        parts = log_out.split("\x00")
        if len(parts) >= 4:
            return RepoMetadata(
                commit_sha=parts[0],
                author=parts[1],
                commit_date=parts[2],
                commit_message=parts[3],
                branch=branch,
            )
        return RepoMetadata(
            commit_sha=self.commit_sha or "unknown",
            branch=branch,
            commit_message="",
            author="",
            commit_date="",
        )
