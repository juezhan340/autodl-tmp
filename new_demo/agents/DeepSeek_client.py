"""OpenAI 兼容 DeepSeek 客户端。A 与 external 都不写 max_tokens。"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


class DeepSeekAPIError(RuntimeError):
    """传输或服务端失败。"""

    def __init__(self, message: str, *, code: str = "SERVICE_ERROR") -> None:
        """保存稳定错误码，供路由使用。"""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DeepSeekResponse:
    """一次 completion 的非敏感元数据和正文。"""

    request_id: str
    role: str
    content: str
    raw_response: dict[str, Any]
    usage: dict[str, Any]
    elapsed_ms: float
    model: str


class DeepSeekClient:
    """读 new_demo/.env.deepseek，原始响应写入 data_raw/api/。"""

    def __init__(
        self,
        env_path: str | Path | None = None,
        *,
        raw_dir: str | Path | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        model: str | None = None,
    ) -> None:
        """读取配置，不把 API key 放进可序列化记录。"""
        config = _load_env_file(Path(env_path) if env_path else _default_env_path())
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", config.get("DEEPSEEK_API_KEY", ""))
        self.base_url = os.environ.get(
            "DEEPSEEK_BASE_URL", config.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        ).rstrip("/")
        self.default_model = model or os.environ.get(
            "DEEPSEEK_MODEL", config.get("DEEPSEEK_MODEL", "deepseek-chat")
        )
        self.a_model = os.environ.get("DEEPSEEK_A_MODEL", config.get("DEEPSEEK_A_MODEL", self.default_model))
        self.external_model = os.environ.get(
            "DEEPSEEK_EXTERNAL_MODEL", config.get("DEEPSEEK_EXTERNAL_MODEL", self.default_model)
        )
        self.timeout = float(
            timeout if timeout is not None else os.environ.get("DEEPSEEK_TIMEOUT", config.get("DEEPSEEK_TIMEOUT", "120"))
        )
        self.max_retries = int(
            max_retries
            if max_retries is not None
            else os.environ.get("DEEPSEEK_MAX_RETRIES", config.get("DEEPSEEK_MAX_RETRIES", "3"))
        )
        self.a_temperature = float(
            os.environ.get("DEEPSEEK_A_TEMPERATURE", config.get("DEEPSEEK_A_TEMPERATURE", "0.6"))
        )
        self.external_temperature = float(
            os.environ.get("DEEPSEEK_EXTERNAL_TEMPERATURE", config.get("DEEPSEEK_EXTERNAL_TEMPERATURE", "0.7"))
        )
        self.raw_dir = Path(raw_dir) if raw_dir else None
        self._lock = threading.Lock()

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        role: str,
        request_id: str | None = None,
        temperature: float | None = None,
    ) -> DeepSeekResponse:
        """发一次 chat completion。请求体不带 max_tokens。"""
        if not self.api_key:
            raise DeepSeekAPIError("DEEPSEEK_API_KEY is empty", code="CONFIG_ERROR")
        if role not in {"A", "external"}:
            raise DeepSeekAPIError(f"unknown role: {role}", code="CONFIG_ERROR")
        req_id = request_id or f"{role}_{uuid.uuid4().hex[:8]}"
        model = self.a_model if role == "A" else self.external_model
        temp = (
            self.a_temperature if role == "A" else self.external_temperature
        ) if temperature is None else temperature
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temp,
        }
        started = time.perf_counter()
        last_error: DeepSeekAPIError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = self._post(payload)
                content = _extract_content(raw)
                elapsed = (time.perf_counter() - started) * 1000.0
                response = DeepSeekResponse(
                    request_id=req_id,
                    role=role,
                    content=content,
                    raw_response=raw,
                    usage=raw.get("usage") if isinstance(raw.get("usage"), dict) else {},
                    elapsed_ms=elapsed,
                    model=model,
                )
                self._write_record(
                    "completions",
                    {
                        "request_id": req_id,
                        "role": role,
                        "model": model,
                        "usage": response.usage,
                        "elapsed_ms": elapsed,
                        "content": content,
                    },
                )
                return response
            except DeepSeekAPIError as exc:
                last_error = exc
                if not _retryable(exc.code) or attempt >= self.max_retries:
                    self._write_record(
                        "errors",
                        {"request_id": req_id, "role": role, "code": exc.code, "message": str(exc)},
                    )
                    raise
                time.sleep(min(2 ** attempt, 8))
        assert last_error is not None
        raise last_error

    def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        role: str,
        request_id: str | None = None,
        temperature: float | None = None,
    ) -> tuple[DeepSeekResponse, dict[str, Any]]:
        """要求正文是一个 JSON 对象。"""
        response = self.complete(messages, role=role, request_id=request_id, temperature=temperature)
        try:
            parsed = _parse_json_object(response.content)
        except ValueError as exc:
            raise DeepSeekAPIError(
                f"{role} response is not valid JSON: {exc}",
                code="INVALID_MODEL_JSON",
            ) from exc
        return response, parsed

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/chat/completions。"""
        if "max_tokens" in payload:
            raise DeepSeekAPIError("max_tokens must not be set", code="CONFIG_ERROR")
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/v1/chat/completions"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            code = f"HTTP_{exc.code}"
            raise DeepSeekAPIError(f"DeepSeek HTTP {exc.code}", code=code) from exc
        except error.URLError as exc:
            raise DeepSeekAPIError(f"DeepSeek network error: {exc.reason}", code="NETWORK_ERROR") from exc
        except TimeoutError as exc:
            raise DeepSeekAPIError("DeepSeek timeout", code="HTTP_408") from exc
        if not isinstance(raw, dict):
            raise DeepSeekAPIError("DeepSeek response is not an object", code="SERVICE_ERROR")
        return raw

    def _write_record(self, name: str, record: dict[str, Any]) -> None:
        """追加不含密钥的 JSONL。"""
        if self.raw_dir is None:
            return
        target = self.raw_dir / f"{name}.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _default_env_path() -> Path:
    """新包默认配置路径。"""
    return Path(__file__).resolve().parents[1] / ".env.deepseek"


def _load_env_file(path: Path) -> dict[str, str]:
    """读 KEY=VALUE，忽略注释。"""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _extract_content(response: dict[str, Any]) -> str:
    """从 OpenAI 兼容返回取出 assistant 文本。"""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DeepSeekAPIError("DeepSeek response has no choices", code="SERVICE_ERROR")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise DeepSeekAPIError("DeepSeek message.content is not a string", code="SERVICE_ERROR")
    return content


def _parse_json_object(content: str) -> dict[str, Any]:
    """兼容纯 JSON 和 markdown 围栏。"""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("JSON result must be an object")
    return parsed


def _retryable(code: str) -> bool:
    """网络和 5xx 才重试。"""
    return code in {"NETWORK_ERROR", "HTTP_408", "HTTP_429", "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504"}
