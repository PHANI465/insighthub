"""
backend/app/api/powerbi.py

Power BI embedded report routes — App-Owns-Data pattern.

  GET /api/powerbi/embed-token   → generate an embed token for the frontend

App-Owns-Data flow
──────────────────
  1. Backend authenticates to Azure AD as a service principal
     (POWERBI_CLIENT_ID + POWERBI_CLIENT_SECRET + POWERBI_TENANT_ID)
  2. Backend calls Power BI REST API to generate an embed token
     for the specified report and workspace
  3. Frontend receives the embed token and renders the report
     using powerbi-client-react (no user-level Azure AD auth needed)

This pattern is preferred over User-Owns-Data for embedded analytics
because end users don't need Power BI Pro licences.

Full Phase 5 implementation adds DAX measures, RLS configuration,
and the React EmbedFrame component.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import require_role
from app.core.appinsights import track_event
from app.core.config import get_settings
from app.models.schemas import EmbedTokenRequest, EmbedTokenResponse, UserInfo

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/powerbi", tags=["Power BI"])
settings = get_settings()

_analyst = require_role("Analyst")


def _get_powerbi_access_token() -> str:
    """
    Acquire an Azure AD access token for the Power BI REST API
    using client credentials (service principal) flow via MSAL.

    Raises HTTPException 503 if Power BI credentials are not configured.
    """
    if not all([
        settings.powerbi_client_id,
        settings.powerbi_client_secret,
        settings.powerbi_tenant_id,
    ]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Power BI credentials not configured. "
                "Set POWERBI_CLIENT_ID, POWERBI_CLIENT_SECRET, POWERBI_TENANT_ID in .env."
            ),
        )
    try:
        import msal

        authority = f"https://login.microsoftonline.com/{settings.powerbi_tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=settings.powerbi_client_id,
            client_credential=settings.powerbi_client_secret,
            authority=authority,
        )
        scope = ["https://analysis.windows.net/powerbi/api/.default"]
        result = app.acquire_token_for_client(scopes=scope)

        if "access_token" not in result:
            error = result.get("error_description", "Unknown MSAL error")
            log.error("Power BI MSAL auth failed: %s", error)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not authenticate with Power BI service. Check service principal credentials.",
            )
        return result["access_token"]

    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="msal package not installed. Add msal to requirements.txt.",
        )


def _generate_embed_token(
    access_token: str,
    workspace_id: str,
    report_id: str,
) -> dict:
    """
    Call Power BI REST API to generate an embed token.
    Returns the API response dict.
    """
    import requests

    url = (
        f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}"
        f"/reports/{report_id}/GenerateToken"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {"accessLevel": "View"}

    resp = requests.post(url, headers=headers, json=body, timeout=30)

    if resp.status_code != 200:
        log.error(
            "Power BI GenerateToken failed: %s %s",
            resp.status_code, resp.text[:200],
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Power BI embed token generation failed: {resp.status_code}",
        )
    return resp.json()


@router.get(
    "/embed-token",
    response_model=EmbedTokenResponse,
    summary="Generate a Power BI embed token",
    description=(
        "Returns an embed token and embed URL for the React frontend to render "
        "a Power BI report. Uses App-Owns-Data service principal auth. "
        "Full DAX measures and RLS setup in Phase 5."
    ),
)
def get_embed_token(
    report_id: Optional[str] = Query(None, description="Override default report ID"),
    workspace_id: Optional[str] = Query(None, description="Override default workspace ID"),
    _user: UserInfo = Depends(_analyst),
) -> EmbedTokenResponse:
    """
    Generate a Power BI embed token for the authenticated user.
    The token is scoped to View access on the specified report.
    """
    r_id = report_id or settings.powerbi_report_id
    w_id = workspace_id or settings.powerbi_workspace_id

    if not r_id or not w_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="POWERBI_REPORT_ID and POWERBI_WORKSPACE_ID must be set in .env.",
        )

    access_token = _get_powerbi_access_token()
    token_data   = _generate_embed_token(access_token, w_id, r_id)

    embed_url = (
        f"https://app.powerbi.com/reportEmbed"
        f"?reportId={r_id}&groupId={w_id}&config=eyJjbHVzdGVyVXJsIjoiaHR0cHM6Ly9XQUJJLVdFU1QtRVVST1BFLXJlZGlyZWN0LmFuYWx5c2lzLndpbmRvd3MubmV0In0%3D"
    )

    track_event(
        "EmbedTokenRequested",
        {"report_id": r_id, "workspace_id": w_id, "user": _user.username},
    )

    return EmbedTokenResponse(
        embed_token=token_data.get("token", ""),
        embed_url=embed_url,
        report_id=r_id,
        workspace_id=w_id,
        expiry=datetime.fromisoformat(
            token_data.get("expiration", datetime.now(timezone.utc).isoformat())
        ),
        token_id=token_data.get("tokenId", str(uuid4())),
    )
