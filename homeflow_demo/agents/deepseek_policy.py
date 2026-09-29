"""提供逐 turn 调用 DeepSeek 的 A 模块策略适配器。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from .deepseek_client import DeepSeekClient


POLICY_SYSTEM = """你是 HomeFlow Demo 的外部策略模型。
每次只输出一个 JSON 工具调用，不能输出多个调用，不能输出解释性文字。
格式必须是 {\"name\":\"工具名\",\"arguments\":{...},\"call_id\":\"本轮唯一字符串\"}。
工具调用必须使用当前上下文的公开 schema。
observe_home 不返回 device_id。要拿到设备 id，需要 inspect_room。环境不会因为没先观察而拒绝 execute_action。
传感器是只读设备，不能对传感器执行写操作。
查询任务用 finish.outcome=answered 并填写结构化 facts；拒绝任务用 finish.outcome=refused、reason_code 和未执行说明；控制任务用 finish.outcome=completed。
不要重复总结已经确认的信息；只给当前一步所需的工具调用。
"""


class DeepSeekPolicy:
    """把 C context 转为 DeepSeek chat 请求并返回 OpenAI 兼容响应。"""

    def __init__(self, client: DeepSeekClient, *, model_id: str | None = None) -> None:
        """保存共享客户端和轨迹中的策略模型标识。"""
        self.client = client
        self.model_id = model_id or client.model

    def respond(self, context: dict[str, Any]) -> dict[str, Any]:
        """为 C 的一个 turn 请求一个 assistant 响应。"""
        turn_index = int(context.get("turn_index", 0))
        request_id = f"policy_turn_{turn_index}_{uuid.uuid4().hex[:10]}"
        messages = [
            {"role": "system", "content": POLICY_SYSTEM},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False, sort_keys=True)},
        ]
        response = self.client.complete(
            messages,
            role="policy",
            request_id=request_id,
            temperature=0.2,
        )
        return response.raw_response
