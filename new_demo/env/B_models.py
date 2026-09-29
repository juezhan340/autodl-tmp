"""定义家庭、场景、工具调用和 B 执行结果的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


JsonDict = dict[str, Any]


def copy_json(value: Any) -> Any:
    """递归复制 JSON，避免外部改到内部状态。"""
    if isinstance(value, dict):
        return {str(key): copy_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [copy_json(item) for item in value]
    return value


@dataclass(frozen=True)
class ParameterSchema:
    """一个设备动作参数的类型、范围、步长或枚举。"""

    type: str
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    enum: tuple[Any, ...] = ()
    description: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ParameterSchema":
        """从动作 params 里读出一个参数约束。"""
        return cls(
            type=str(data["type"]),
            required=bool(data.get("required", True)),
            minimum=data.get("minimum"),
            maximum=data.get("maximum"),
            step=data.get("step"),
            enum=tuple(copy_json(data.get("enum", []))),
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> JsonDict:
        """输出给 inspect_device 看的参数 schema。"""
        result: JsonDict = {"type": self.type, "required": self.required}
        if self.minimum is not None:
            result["minimum"] = self.minimum
        if self.maximum is not None:
            result["maximum"] = self.maximum
        if self.step is not None:
            result["step"] = self.step
        if self.enum:
            result["enum"] = list(self.enum)
        if self.description:
            result["description"] = self.description
        return result


@dataclass(frozen=True)
class ActionSchema:
    """一台设备允许执行的一个动作及其参数。"""

    action: str
    params: dict[str, ParameterSchema] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ActionSchema":
        """从设备 JSON 读动作名和参数。"""
        raw_params = data.get("params", {})
        return cls(
            action=str(data["action"]),
            params={str(name): ParameterSchema.from_dict(spec) for name, spec in raw_params.items()},
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> JsonDict:
        """输出公开动作 schema。"""
        result: JsonDict = {
            "action": self.action,
            "params": {name: spec.to_dict() for name, spec in self.params.items()},
        }
        if self.description:
            result["description"] = self.description
        return result


@dataclass(frozen=True)
class Room:
    """一级房间和它挂着的设备 id。"""

    room_id: str
    display_name: str
    device_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: JsonDict) -> "Room":
        """从场景字典构造房间。"""
        return cls(
            room_id=str(data["room_id"]),
            display_name=str(data["display_name"]),
            device_ids=tuple(str(item) for item in data.get("device_ids", [])),
        )

    def to_dict(self) -> JsonDict:
        """把房间写成 JSON。"""
        return {
            "room_id": self.room_id,
            "display_name": self.display_name,
            "device_ids": list(self.device_ids),
        }


@dataclass(frozen=True)
class Device:
    """一台传感器或可控设备。"""

    device_id: str
    room_id: str
    display_name: str
    kind: str
    device_type: str
    state: JsonDict
    actions: tuple[ActionSchema, ...] = ()
    available: bool = True

    @classmethod
    def from_dict(cls, data: JsonDict) -> "Device":
        """从场景字典构造设备并复制当前状态。"""
        return cls(
            device_id=str(data["device_id"]),
            room_id=str(data["room_id"]),
            display_name=str(data["display_name"]),
            kind=str(data["kind"]),
            device_type=str(data["device_type"]),
            state=copy_json(data.get("state", {})),
            actions=tuple(ActionSchema.from_dict(item) for item in data.get("actions", [])),
            available=bool(data.get("available", True)),
        )

    def to_dict(self) -> JsonDict:
        """把设备写成 JSON，含 actions。"""
        return {
            "device_id": self.device_id,
            "room_id": self.room_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "device_type": self.device_type,
            "state": copy_json(self.state),
            "actions": [item.to_dict() for item in self.actions],
            "available": self.available,
        }


@dataclass(frozen=True)
class Home:
    """按 id 索引的房间和设备快照。"""

    rooms: dict[str, Room]
    devices: dict[str, Device]

    @classmethod
    def from_dict(cls, data: JsonDict) -> "Home":
        """从 rooms/devices 数组建立索引。"""
        rooms = [Room.from_dict(item) for item in data.get("rooms", [])]
        devices = [Device.from_dict(item) for item in data.get("devices", [])]
        return cls(
            rooms={item.room_id: item for item in rooms},
            devices={item.device_id: item for item in devices},
        )

    def to_dict(self) -> JsonDict:
        """按 id 排序输出家庭快照。"""
        return {
            "rooms": [self.rooms[key].to_dict() for key in sorted(self.rooms)],
            "devices": [self.devices[key].to_dict() for key in sorted(self.devices)],
        }


@dataclass(frozen=True)
class StateCondition:
    """隐藏任务里一个设备字段的比较条件。"""

    device_id: str
    field: str
    operator: str
    value: Any

    @classmethod
    def from_dict(cls, data: JsonDict) -> "StateCondition":
        """从 conditions/keep 项构造比较条件。"""
        return cls(
            device_id=str(data["device_id"]),
            field=str(data["field"]),
            operator=str(data.get("operator", "eq")),
            value=copy_json(data.get("value", data.get("equals"))),
        )

    def to_dict(self) -> JsonDict:
        """把隐藏条件写成 JSON。"""
        return {
            "device_id": self.device_id,
            "field": self.field,
            "operator": self.operator,
            "value": copy_json(self.value),
        }


@dataclass(frozen=True)
class TaskSpec:
    """只给 C 审查用的隐藏目标；A 看不见。"""

    intent: str
    conditions: tuple[StateCondition, ...]
    keep: tuple[StateCondition, ...] = ()
    required_observations: tuple[JsonDict, ...] = ()
    expected_finish: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict) -> "TaskSpec":
        """从 task 对象读取 intent、条件和 finish 契约。"""
        return cls(
            intent=str(data.get("intent", "")),
            conditions=tuple(StateCondition.from_dict(item) for item in data.get("conditions", [])),
            keep=tuple(StateCondition.from_dict(item) for item in data.get("keep", [])),
            required_observations=tuple(copy_json(item) for item in data.get("required_observations", [])),
            expected_finish=copy_json(data.get("expected_finish", {})),
        )

    def to_dict(self) -> JsonDict:
        """把隐藏任务写成 JSON，不含用户那句话。"""
        return {
            "intent": self.intent,
            "conditions": [item.to_dict() for item in self.conditions],
            "keep": [item.to_dict() for item in self.keep],
            "required_observations": copy_json(list(self.required_observations)),
            "expected_finish": copy_json(self.expected_finish),
        }


@dataclass(frozen=True)
class EpisodeConfig:
    """C 的回合数和每轮工具上限。"""

    max_turns: int = 10
    max_tool_calls_per_turn: int = 1

    @classmethod
    def from_dict(cls, data: JsonDict) -> "EpisodeConfig":
        """从场景读回合控制；缺省每轮 1 个工具。"""
        return cls(
            max_turns=int(data.get("max_turns", 10)),
            max_tool_calls_per_turn=int(data.get("max_tool_calls_per_turn", 1)),
        )

    def to_dict(self) -> JsonDict:
        """把回合参数写成字典。"""
        return {
            "max_turns": self.max_turns,
            "max_tool_calls_per_turn": self.max_tool_calls_per_turn,
        }


@dataclass(frozen=True)
class Scenario:
    """C.run 的六项输入：id、蓝图追溯、家、用户话、隐藏任务、回合配置。"""

    scenario_id: str
    blueprint_id: str
    home: Home
    user_request: str
    task: TaskSpec
    episode_config: EpisodeConfig

    @classmethod
    def from_dict(cls, data: JsonDict) -> "Scenario":
        """从已通过 schema 的字典构造场景。"""
        return cls(
            scenario_id=str(data["scenario_id"]),
            blueprint_id=str(data["blueprint_id"]),
            home=Home.from_dict(data["home"]),
            user_request=str(data["user_request"]),
            task=TaskSpec.from_dict(data["task"]),
            episode_config=EpisodeConfig.from_dict(data.get("episode_config", {})),
        )

    def to_dict(self) -> JsonDict:
        """把场景写成可重放 JSON。"""
        return {
            "scenario_id": self.scenario_id,
            "blueprint_id": self.blueprint_id,
            "home": self.home.to_dict(),
            "user_request": self.user_request,
            "task": self.task.to_dict(),
            "episode_config": self.episode_config.to_dict(),
        }


@dataclass(frozen=True)
class ToolCall:
    """C 从 A 响应里抽出的一次工具调用。"""

    name: str
    arguments: JsonDict = field(default_factory=dict)
    call_id: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ToolCall":
        """从字典保留原始字段，交给工具 schema 判错。"""
        if not isinstance(data, dict):
            raise TypeError("tool call must be an object")
        arguments = data.get("arguments", {})
        return cls(
            name=data.get("name", ""),
            arguments=copy_json(arguments),
            call_id=data.get("call_id", data.get("id", "")),
        )

    def to_dict(self) -> JsonDict:
        """输出统一工具调用。"""
        return {
            "name": self.name,
            "arguments": copy_json(self.arguments),
            "call_id": self.call_id,
        }


@dataclass(frozen=True)
class AssistantTurn:
    """C 解析后的一次 A 决策。"""

    tool_calls: tuple[ToolCall, ...] = ()
    text: str = ""
    raw_response: Any = None
    parse_errors: tuple[str, ...] = ()

    def to_dict(self) -> JsonDict:
        """把一次 A 决策写成轨迹字段。"""
        return {
            "tool_calls": [item.to_dict() for item in self.tool_calls],
            "text": self.text,
            "raw_response": copy_json(self.raw_response),
            "parse_errors": list(self.parse_errors),
        }


@dataclass(frozen=True)
class ToolEvent:
    """B 执行一个家庭工具，或 C 收下 finish 后的事件。"""

    call_id: str
    tool_name: str
    arguments: JsonDict
    result: JsonDict
    state_diff: JsonDict

    @property
    def ok(self) -> bool:
        """读统一外壳里的 ok。"""
        return bool(self.result.get("ok"))

    @property
    def error_code(self) -> str | None:
        """失败时返回错误码。"""
        error = self.result.get("error")
        return str(error.get("code")) if isinstance(error, dict) and error.get("code") else None

    def to_dict(self) -> JsonDict:
        """把工具事件写成可审计字典。"""
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": copy_json(self.arguments),
            "result": copy_json(self.result),
            "state_diff": copy_json(self.state_diff),
        }


@dataclass(frozen=True)
class EnvStepResult:
    """B.step 的返回：新 observation 和这一次 event。"""

    observation: JsonDict
    event: ToolEvent

    def to_dict(self) -> JsonDict:
        """把环境一步结果写成字典。"""
        return {"observation": copy_json(self.observation), "event": self.event.to_dict()}
