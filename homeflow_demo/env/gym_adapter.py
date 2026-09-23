"""提供不强依赖 Gymnasium 的 HomeEnv 标准适配器。"""

from __future__ import annotations

from typing import Any

from .home_env import HomeEpisodeEnv
from .models import Action, AssistantTurn


class GymHomeEnvAdapter:
    """把 HomeEpisodeEnv 映射到 Gymnasium 风格的 reset/step 接口。"""

    def __init__(self, core: HomeEpisodeEnv | None = None) -> None:
        """创建适配器，允许外部注入已有核心环境。"""
        self.core = core or HomeEpisodeEnv()

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """按 Gymnasium 语义加载 options.scenario 并返回 observation/info。"""
        if not options or "scenario" not in options:
            raise ValueError("options.scenario is required for GymHomeEnvAdapter.reset")
        return self.core.reset(options["scenario"], seed=seed)

    def step(
        self,
        action: AssistantTurn | Action | dict[str, Any] | str,
    ) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        """按 Gymnasium 五元组返回一次 assistant turn 转移。"""
        result = self.core.step(action)
        return result.observation, result.reward, result.terminated, result.truncated, result.info

    def render(self) -> dict[str, Any]:
        """返回当前环境状态，供调试器使用。"""
        return {"devices": self.core.devices, "trajectory": self.core.trajectory()}

    def close(self) -> None:
        """关闭适配器；当前核心环境没有外部资源需要释放。"""
        return None
