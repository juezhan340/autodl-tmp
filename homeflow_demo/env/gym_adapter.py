"""提供围绕 V1.2 HomeEnv 的可选 Gymnasium 风格薄适配器。"""

from __future__ import annotations

from typing import Any

from .home_env import HomeEnv
from .models import ToolCall


class GymHomeEnvAdapter:
    """把 B 模块映射为 reset/step 五元组，不在环境内复制奖励逻辑。"""

    def __init__(self, core: HomeEnv | None = None) -> None:
        """允许注入已有 HomeEnv，默认创建新实例。"""
        self.core = core or HomeEnv()

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """从 options.scenario 加载静态场景。"""
        if not options or "scenario" not in options:
            raise ValueError("options.scenario is required")
        return self.core.reset(options["scenario"], seed=seed)

    def step(
        self,
        action: ToolCall | dict[str, Any],
    ) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        """执行单个 ToolCall；reward 和终止由外层 C 决定，故此处保持中性。"""
        result = self.core.step(action)
        return result.observation, 0.0, False, False, {"tool_event": result.event.to_dict()}

    def render(self) -> dict[str, Any]:
        """返回当前运行状态和工具事件，供调试查看。"""
        return {"runtime_state": self.core.runtime_state, "events": self.core.events()}

    def close(self) -> None:
        """当前内存环境没有外部资源需要释放。"""
        return None
