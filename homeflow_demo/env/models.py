"""HomeEnv 使用的场景、动作和结果数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class GoalPredicate:
    """描述一个设备字段必须满足的目标条件。"""

    device_id: str
    field: str
    equals: Any

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalPredicate":
        """从 JSON 对象构造目标谓词。"""
        return cls(
            device_id=str(data["device_id"]),
            field=str(data["field"]),
            equals=data["equals"],
        )


@dataclass
class Scenario:
    """保存一个 HomeEnv episode 的静态输入。"""

    scenario_id: str
    user_request: str
    devices: list[dict[str, Any]]
    predicates: list[GoalPredicate]
    max_steps: int = 6
    max_tool_calls_per_turn: int = 4
    seed: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        """从可序列化字典构造场景并校验基本字段。"""
        goal = data.get("goal", {})
        predicates = [GoalPredicate.from_dict(item) for item in goal.get("predicates", [])]
        # 旧 V1 数据若同时带有两个字段，以显式 max_steps 兼容旧调用方。
        max_turns = int(data["max_steps"] if "max_steps" in data else data.get("max_turns", 6))
        max_tool_calls_per_turn = int(data.get("max_tool_calls_per_turn", 4))
        if max_turns <= 0:
            raise ValueError("max_turns must be positive")
        if max_tool_calls_per_turn <= 0:
            raise ValueError("max_tool_calls_per_turn must be positive")
        devices = data.get("devices", [])
        if not isinstance(devices, list) or not devices:
            raise ValueError("scenario.devices must be a non-empty list")
        return cls(
            scenario_id=str(data["scenario_id"]),
            user_request=str(data["user_request"]),
            devices=devices,
            predicates=predicates,
            max_steps=max_turns,
            max_tool_calls_per_turn=max_tool_calls_per_turn,
            seed=data.get("seed"),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """把场景转换成可保存为 JSON 的字典。"""
        result = asdict(self)
        result["goal"] = {"predicates": result.pop("predicates")}
        result["max_turns"] = result.pop("max_steps")
        return result

    @property
    def max_turns(self) -> int:
        """返回 V1.1 的模型决策步上限。"""
        return self.max_steps


@dataclass(frozen=True)
class Action:
    """表示模型提交给环境的一次结构化工具动作。"""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        """从工具调用字典构造动作。"""
        if not isinstance(data, dict):
            raise TypeError("action must be a dictionary")
        return cls(name=str(data.get("name", "")), arguments=dict(data.get("arguments", {})))

    def to_dict(self) -> dict[str, Any]:
        """把原子工具动作转换成可写入 JSON 的字典。"""
        return {"name": self.name, "arguments": deepcopy_json_value(self.arguments)}


@dataclass
class AssistantTurn:
    """表示一次模型 assistant 输出及其中包含的工具调用。"""

    tool_calls: list[Action] = field(default_factory=list)
    text: str = ""
    assistant_output: Any = None
    parse_errors: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssistantTurn":
        """从结构化 assistant 输出构造一个模型决策步。"""
        if not isinstance(data, dict):
            raise TypeError("assistant turn must be a dictionary")
        raw_calls = data.get("tool_calls", [])
        if not isinstance(raw_calls, list):
            raise ValueError("assistant turn tool_calls must be a list")
        calls = [Action.from_dict(item) for item in raw_calls]
        text = data.get("text", "")
        if not isinstance(text, str):
            raise ValueError("assistant turn text must be a string")
        return cls(
            tool_calls=calls,
            text=text,
            assistant_output=deepcopy_json_value(data.get("assistant_output")),
        )

    def to_dict(self) -> dict[str, Any]:
        """把 assistant turn 转换成统一的结构化输出。"""
        output: dict[str, Any] = {
            "tool_calls": [action.to_dict() for action in self.tool_calls],
            "text": self.text,
        }
        if self.assistant_output is not None:
            output["assistant_output"] = deepcopy_json_value(self.assistant_output)
        return output


@dataclass
class ToolEvent:
    """保存一个 turn 内单个工具调用的执行审计信息。"""

    tool_event_index: int
    action: dict[str, Any]
    valid: bool
    ok: bool
    result: dict[str, Any]
    completion_before: float
    completion_after: float
    error_code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """把工具事件转换成可序列化字典。"""
        return deepcopy_json_value(asdict(self))


@dataclass
class TurnResult:
    """保存一次模型 turn 聚合后的环境反馈。"""

    turn_index: int
    assistant_output: Any
    tool_calls: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    observation_before: dict[str, Any]
    observation_after: dict[str, Any]
    reward: float
    reward_components: dict[str, float]
    terminated: bool
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        """把 turn 结果转换成可写入轨迹的字典。"""
        return deepcopy_json_value(asdict(self))


@dataclass
class StepResult:
    """保存一次环境 step 的完整返回值。"""

    observation: dict[str, Any]
    reward: float
    terminated: bool
    truncated: bool
    info: dict[str, Any]


@dataclass
class FinalResult:
    """保存 episode 结束时的可评测结果。"""

    scenario_id: str
    success: bool
    completion: float
    steps: int
    terminated: bool
    truncated: bool
    failure_reason: str | None
    final_state: dict[str, dict[str, Any]]

    @property
    def turns(self) -> int:
        """返回 V1.1 的模型 turn 数。"""
        return self.steps


@dataclass
class PredicateResult:
    """保存目标谓词评估结果。"""

    completion: float
    satisfied: list[dict[str, Any]]
    unsatisfied: list[dict[str, Any]]

    @property
    def success(self) -> bool:
        """判断所有目标谓词是否满足。"""
        return bool(self.satisfied) and not self.unsatisfied


def deepcopy_json_value(value: Any) -> Any:
    """复制轨迹中的 JSON 值，避免调用方修改环境内部对象。"""
    if isinstance(value, dict):
        return {str(key): deepcopy_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [deepcopy_json_value(item) for item in value]
    return value
