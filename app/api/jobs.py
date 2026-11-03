"""Analyze a confirmed resume against pasted JD text in one request."""

from fastapi import APIRouter, Request

from app.schemas.business import MatchInput, MatchResponse
from app.services.match_service import MatchService

router = APIRouter(prefix="/api/jobs", tags=["analysis"])


@router.post("/match", response_model=MatchResponse)
def match(body: MatchInput, request: Request) -> MatchResponse:
    return MatchService(request.app.state.store, request.app.state.model).analyze(body.resume_id, body.jd_text, body.resume_revision)
