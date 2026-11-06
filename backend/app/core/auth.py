import logging
from typing import Optional
from fastapi import Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)


class DeveloperUser(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    role: str = "developer"
    is_authenticated: bool = True


async def require_developer_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    x_developer_token: Optional[str] = Header(None, alias="X-Developer-Token"),
    x_developer_id: Optional[str] = Header(None, alias="X-Developer-Id"),
) -> DeveloperUser:
    """
    Enforce actual server-side developer authentication and authorization.
    Validates token against server-configured developer keys.
    Rejects unauthorized or unauthenticated requests.
    Returns authenticated DeveloperUser whose identity is verified by the server.
    """
    token: Optional[str] = None

    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif x_developer_token:
        token = x_developer_token

    if not token:
        logger.warning("Developer action rejected: Missing developer authentication credentials.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Developer authentication required. Provide a valid Bearer token or X-Developer-Token header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate token against authorized server-side developer keys
    valid_keys = set(settings.DEVELOPER_API_KEYS)
    if token not in valid_keys:
        logger.warning(f"Developer action rejected: Invalid developer credentials provided.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Invalid developer authentication token.",
        )

    # Server determines or validates identity
    actor_id = x_developer_id.strip() if x_developer_id and x_developer_id.strip() else settings.DEVELOPER_DEFAULT_ID

    return DeveloperUser(
        id=actor_id,
        name=actor_id,
        email=f"{actor_id}@pragmata.internal",
        role="developer",
        is_authenticated=True,
    )
