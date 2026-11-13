"""Unified error format: {"error": {"code", "message", "detail"}} (spec 1.4, 7)."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# code -> (status, message)
ERRORS: dict[str, tuple[int, str]] = {
    # auth
    "INVALID_CREDENTIALS": (401, "학번 또는 비밀번호가 올바르지 않습니다."),
    "INVALID_TOKEN": (401, "로그인이 만료되었습니다. 다시 로그인해 주세요."),
    "FORBIDDEN": (403, "권한이 없습니다."),
    "ACCOUNT_DISABLED": (403, "비활성화된 계정입니다. 담당 선생님께 문의해 주세요."),
    "TOO_MANY_ATTEMPTS": (429, "로그인 시도가 너무 많습니다. 10분 후 다시 시도해 주세요."),
    # signup
    "STUDENT_NOT_ALLOWED": (404, "재학생 명단에 없는 학번입니다."),
    "STUDENT_NAME_MISMATCH": (400, "학번과 이름이 일치하지 않습니다."),
    "STUDENT_ALREADY_REGISTERED": (409, "이미 가입된 학번입니다."),
    "WEAK_PASSWORD": (422, "비밀번호는 8자 이상, 영문과 숫자를 포함해야 합니다."),
    "PRIVACY_NOT_AGREED": (400, "개인정보 수집·이용에 동의해 주세요."),
    # polls
    "POLL_NOT_FOUND": (404, "투표를 찾을 수 없습니다."),
    "POLL_NOT_OPEN": (403, "진행 중인 투표가 아닙니다."),
    "INVALID_OPTION": (400, "올바르지 않은 선택지입니다."),
    "VOTE_ALREADY_CAST": (409, "이미 투표에 참여했습니다."),
    "VOTE_NOT_FOUND": (404, "아직 투표에 참여하지 않았습니다."),
    "VOTE_CHANGE_DISABLED": (403, "투표 변경이 허용되지 않습니다."),
    "RESULT_NOT_AVAILABLE": (403, "투표 마감 후 결과가 공개됩니다."),
    "POLL_HAS_VOTES": (409, "참여 기록이 있어 삭제할 수 없습니다."),
    "POLL_ALREADY_STARTED": (409, "투표가 시작되어 선택지를 변경할 수 없습니다."),
    "INVALID_PERIOD": (400, "마감 시각은 시작 시각보다 늦어야 합니다."),
    "TOO_FEW_OPTIONS": (400, "선택지는 2개 이상이어야 합니다."),
    # meals
    "SIGNUP_DEADLINE_PASSED": (403, "신청이 마감되었습니다."),
    "MEAL_NOT_AVAILABLE": (400, "해당 날짜에는 급식이 운영되지 않습니다."),
    "DATE_OUT_OF_RANGE": (400, "급식 제공일 14일 전부터 신청할 수 있습니다."),
    # common
    "NOT_FOUND": (404, "요청한 리소스를 찾을 수 없습니다."),
    "CONFLICT": (409, "요청이 현재 데이터와 충돌합니다."),
    "VALIDATION_ERROR": (422, "입력값을 확인해 주세요."),
    "RATE_LIMITED": (429, "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."),
    "INTERNAL_ERROR": (500, "일시적인 오류가 발생했습니다."),
}


class AppError(Exception):
    def __init__(self, code: str, detail: Any = None, message: str | None = None):
        status, default_message = ERRORS[code]
        self.code = code
        self.status_code = status
        self.message = message or default_message
        self.detail = detail
        super().__init__(code)


def error_response(code: str, detail: Any = None, message: str | None = None) -> JSONResponse:
    status, default_message = ERRORS[code]
    body = {"error": {"code": code, "message": message or default_message, "detail": detail}}
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(status_code=status, content=body, headers=headers)


_HTTP_STATUS_TO_CODE = {
    401: "INVALID_TOKEN",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.code, exc.detail, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            fields.setdefault(".".join(loc) or "_", []).append(err.get("msg", "invalid"))
        return error_response("VALIDATION_ERROR", {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_TO_CODE.get(exc.status_code)
        if code is None:
            body = {"error": {"code": "HTTP_ERROR", "message": str(exc.detail), "detail": None}}
            return JSONResponse(status_code=exc.status_code, content=body)
        return error_response(code)

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        # Fallback: endpoints with a specific meaning (e.g. VOTE_ALREADY_CAST) catch it themselves.
        logger.info("Unhandled IntegrityError: %s", exc.orig)
        return error_response("CONFLICT")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return error_response("INTERNAL_ERROR")
