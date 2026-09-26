"""提供无第三方依赖的 DeepSeek OpenAI 兼容客户端。"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib import error, request


class DeepSeekAPIError(RuntimeError):
    """表示 DeepSeek 请求在传输或服务端阶段失败。"""

    def __init__(self, message: str, *, code: str = "SERVICE_ERROR") -> None:
        """保存可供数据路由使用的稳定错误码。"""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DeepSeekResponse:
    """保存一次 completion 的非敏感响应元数据和模型正文。"""

    request_id: str
    role: str
    content: str
    raw_response: dict[str, Any]
    usage: dict[str, Any]
    elapsed_ms: float
    model: str


class DeepSeekClient:
    """使用本地 .env.deepseek 调用 DeepSeek 并记录可审计原始响应。"""

    def __init__(
        self,
        env_path: str | Path | None = None,
        *,
        raw_dir: str | Path | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        model: str | None = None,
    ) -> None:
        """读取配置但绝不把 API key 放入对象的可序列化记录。"""
        config = _load_env_file(Path(env_path) if env_path else _default_env_path())
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", config.get("DEEPSEEK_API_KEY", ""))
        self.base_url = os.environ.get(
            "DEEPSEEK_BASE_URL", config.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        ).rstrip("/")
        self.model = model or os.environ.get(
            "DEEPSEEK_MODEL", config.get("DEEPSEEK_MODEL", "deepseek-chat")
        )
        self.timeout = float(timeout if timeout is not None else os.environ.get(
            "DEEPSEEK_TIMEOUT", config.get("DEEPSEEK_TIMEOUT", "120")
        ))
        self.max_retries = int(max_retries if max_retries is not None else os.environ.get(
            "DEEPSEEK_MAX_RETRIES", config.get("DEEPSEEK_MAX_RETRIES", "3")
        ))
        self.temperature = float(os.environ.get(
            "DEEPSEEK_TEMPERATURE", config.get("DEEPSEEK_TEMPERATURE", "0.6")
        ))
        self.max_tokens = int(os.environ.get(
            "DEEPSEEK_MAX_TOKENS", config.get("DEEPSEEK_MAX_TOKENS", "2048")
        ))
        self.raw_dir = Path(raw_dir) if raw_dir else None
        self._lock = threading.Lock()
        self._active_requests = 0
        self._max_active_requests = 0

    @property
    def max_active_requests(self) -> int:
        """返回本客户端观察到的最大并发请求数。"""
        with self._lock:
            return self._max_active_requests

    def complete(
        self,
        messages: Iterable[dict[str, Any]],
        *,
        role: str,
        request_id: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> DeepSeekResponse:
        """执行一次聊天 completion，传输失败时做有限重试并保存原始响应。"""
        if not self.api_key:
            raise DeepSeekAPIError("DEEPSEEK_API_KEY is empty", code="CONFIG_ERROR")
        request_id = request_id or f"ds_{uuid.uuid4().hex}"
        message_list = [dict(item) for item in messages]
        payload = {
            "model": self.model,
            "messages": message_list,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }
        started = time.perf_counter()
        last_error: DeepSeekAPIError | None = None
        self._mark_request_start()
        try:
            for attempt in range(self.max_retries + 1):
                try:
                    response = self._post(payload)
                    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
                    content = _extract_content(response)
                    result = DeepSeekResponse(
                        request_id=request_id,
                        role=role,
                        content=content,
                        raw_response=response,
                        usage=response.get("usage", {}) if isinstance(response, dict) else {},
                        elapsed_ms=elapsed_ms,
                        model=self.model,
                    )
                    self._write_record("responses", {
                        "request_id": request_id,
                        "role": role,
                        "model": self.model,
                        "attempt": attempt,
                        "content": content,
                        "raw_response": response,
                        "usage": result.usage,
                        "elapsed_ms": elapsed_ms,
                        "created_at": time.time(),
                    })
                    return result
                except DeepSeekAPIError as exc:
                    last_error = exc
                    if attempt >= self.max_retries or not _retryable(exc.code):
                        raise
                    time.sleep(min(2.0 ** attempt, 8.0))
            raise last_error or DeepSeekAPIError("DeepSeek request failed")
        finally:
            self._write_record("requests", {
                "request_id": request_id,
                "role": role,
                "model": self.model,
                "messages": message_list,
                "temperature": payload["temperature"],
                "max_tokens": payload["max_tokens"],
                "created_at": time.time(),
            })
            self._mark_request_end()

    def complete_json(
        self,
        messages: Iterable[dict[str, Any]],
        *,
        role: str,
        request_id: str | None = None,
        temperature: float | None = 0.0,
        max_tokens: int | None = None,
    ) -> tuple[DeepSeekResponse, dict[str, Any]]:
        """调用模型并把正文解析为 JSON 对象，解析失败交给上层归类。"""
        response = self.complete(
            messages,
            role=role,
            request_id=request_id,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            parsed = _parse_json_object(response.content)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DeepSeekAPIError(
                f"{role} response is not valid JSON: {exc}",
                code="INVALID_MODEL_JSON",
            ) from exc
        return response, parsed

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """向 DeepSeek chat/completions 端点发送一次 HTTP 请求。"""
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            code = "HTTP_429" if exc.code == 429 else f"HTTP_{exc.code}"
            raise DeepSeekAPIError(f"DeepSeek HTTP {exc.code}", code=code) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise DeepSeekAPIError(f"DeepSeek transport error: {exc}", code="NETWORK_ERROR") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DeepSeekAPIError("DeepSeek response is not JSON", code="SERVICE_ERROR") from exc
        if not isinstance(parsed, dict):
            raise DeepSeekAPIError("DeepSeek response must be an object", code="SERVICE_ERROR")
        if parsed.get("error"):
            raise DeepSeekAPIError(str(parsed["error"]), code="SERVICE_ERROR")
        return parsed

    def _mark_request_start(self) -> None:
        """记录并发计数，供环境端并发 smoke test 读取。"""
        with self._lock:
            self._active_requests += 1
            self._max_active_requests = max(self._max_active_requests, self._active_requests)

    def _mark_request_end(self) -> None:
        """在请求完成后释放并发计数。"""
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    def _write_record(self, name: str, record: dict[str, Any]) -> None:
        """以线程安全方式追加不含密钥的 JSONL 审计记录。"""
        if self.raw_dir is None:
            return
        target = self.raw_dir / f"{name}.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _default_env_path() -> Path:
    """返回仓库内默认 DeepSeek 配置路径。"""
    return Path(__file__).resolve().parents[1] / ".env.deepseek"


def _load_env_file(path: Path) -> dict[str, str]:
    """读取简单 KEY=VALUE 配置，忽略注释和空行。"""
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
    """从 OpenAI 兼容返回中提取 assistant 文本。"""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DeepSeekAPIError("DeepSeek response has no choices", code="SERVICE_ERROR")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise DeepSeekAPIError("DeepSeek message.content is not a string", code="SERVICE_ERROR")
    return content


def _parse_json_object(content: str) -> dict[str, Any]:
    """兼容纯 JSON 和被 markdown code fence 包裹的 JSON。"""
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
    """判断错误是否适合进行传输级重试。"""
    return code in {"NETWORK_ERROR", "HTTP_408", "HTTP_429", "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504"}
