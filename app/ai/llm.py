"""Claude 호출 공통부. 결과는 항상 Pydantic schema로 검증해서 돌려준다."""

from typing import TypeVar

import anthropic
from pydantic import BaseModel

from app.core.config import settings

TIMEOUT_SECONDS = 60.0
T = TypeVar("T", bound=BaseModel)


class AIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise AIError(503, "AI_NOT_CONFIGURED", "ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=TIMEOUT_SECONDS)


def parse[T: BaseModel](
    system: str,
    user: str,
    schema: type[T],
    client: anthropic.Anthropic | None = None,
    max_tokens: int = 16000,
) -> T:
    api = client or _client()
    try:
        response = api.messages.parse(
            model=settings.ai_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
    except anthropic.AuthenticationError as exc:
        raise AIError(503, "AI_NOT_CONFIGURED", "AI API 키를 확인해 주세요.") from exc
    except anthropic.PermissionDeniedError as exc:
        raise AIError(503, "AI_NOT_CONFIGURED", "AI API 키의 권한을 확인해 주세요.") from exc
    except anthropic.RateLimitError as exc:
        raise AIError(
            429, "AI_RATE_LIMITED", "AI 요청이 많습니다. 잠시 후 다시 시도해 주세요."
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise AIError(503, "AI_UNAVAILABLE", "AI 서버에 연결하지 못했습니다.") from exc
    except anthropic.APIStatusError as exc:
        raise AIError(502, "AI_UPSTREAM_ERROR", "AI 서버에서 오류가 발생했습니다.") from exc

    if response.stop_reason == "refusal":
        raise AIError(502, "AI_REFUSED", "AI가 이 요청을 처리하지 않았습니다.")
    if response.stop_reason == "max_tokens":
        raise AIError(502, "AI_OUTPUT_TRUNCATED", "AI 응답이 너무 길어 중간에 끊겼습니다.")
    if response.parsed_output is None:
        raise AIError(502, "AI_BAD_RESPONSE", "AI 응답을 해석하지 못했습니다.")
    return response.parsed_output
