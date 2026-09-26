"""定义 HomeFlow V1.2 的家庭、场景、工具调用和环境结果数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


JsonDict = dict[str, Any]


def copy_json(value: Any) -> Any:
    """递归复制 JSON 值，避免外部调用方修改内部状态。"""
    if isinstance(value, dict):
        return {str(key): copy_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [copy_json(item) for item in value]
    return value


@dataclass(frozen=True)
class ParameterSchema:
    """描述一个设备动作参数的类型、范围、步长或枚举。"""

    type: str
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    enum: tuple[Any, ...] = ()
    description: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ParameterSchema":
        """从可序列化字典构造参数 schema。"""
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
        """输出适合工具展示和 JSON 保存的参数 schema。"""
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
    """描述一台设备允许执行的规范动作及其参数。"""

    action: str
    params: dict[str, ParameterSchema] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ActionSchema":
        """从设备 JSON 中读取动作名称和参数约束。"""
        raw_params = data.get("params", {})
        return cls(
            action=str(data["action"]),
            params={str(name): ParameterSchema.from_dict(spec) for name, spec in raw_params.items()},
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> JsonDict:
        """输出公开给模型和执行器共用的动作 schema。"""
        result: JsonDict = {
            "action": self.action,
            "params": {name: spec.to_dict() for name, spec in self.params.items()},
        }
        if self.description:
            result["description"] = self.description
        return result


@dataclass(frozen=True)
class Room:
    """描述家庭中的一级房间实体和设备归属索引。"""

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
        """把房间转换为 JSON 字典。"""
        return {
            "room_id": self.room_id,
            "display_name": self.display_name,
            "device_ids": list(self.device_ids),
        }


@dataclass(frozen=True)
class Device:
    """描述一台只读传感器或可控执行设备。"""

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
        """从场景字典构造设备并复制状态。"""
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
        """把设备转换为 JSON 字典。"""
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
    """保存按 ID 索引的房间和设备静态快照。"""

    rooms: dict[str, Room]
    devices: dict[str, Device]

    @classmethod
    def from_dict(cls, data: JsonDict) -> "Home":
        """从 rooms/devices 数组建立稳定索引。"""
        rooms = [Room.from_dict(item) for item in data.get("rooms", [])]
        devices = [Device.from_dict(item) for item in data.get("devices", [])]
        return cls(
            rooms={item.room_id: item for item in rooms},
            devices={item.device_id: item for item in devices},
        )

    def to_dict(self) -> JsonDict:
        """按 ID 排序输出家庭静态快照。"""
        return {
            "rooms": [self.rooms[key].to_dict() for key in sorted(self.rooms)],
            "devices": [self.devices[key].to_dict() for key in sorted(self.devices)],
        }


@dataclass(frozen=True)
class StateCondition:
    """描述隐藏任务中一个设备字段需要满足的比较条件。"""

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
        """把隐藏条件转换成可保存字典。"""
        return {
            "device_id": self.device_id,
            "field": self.field,
            "operator": self.operator,
            "value": copy_json(self.value),
        }


@dataclass(frozen=True)
class TaskSpec:
    """保存模型可见请求和只供 C 读取的隐藏目标。"""

    user_request: str
    conditions: tuple[StateCondition, ...]
    keep: tuple[StateCondition, ...] = ()
    category: str | None = None
    required_observations: tuple[JsonDict, ...] = ()
    expected_finish: JsonDict = field(default_factory=dict)
    blueprint_id: str | None = None

    @classmethod
    def from_dict(cls, data: JsonDict) -> "TaskSpec":
        """从 task 对象读取用户请求、目标和保持条件。"""
        return cls(
            user_request=str(data["user_request"]),
            conditions=tuple(StateCondition.from_dict(item) for item in data.get("conditions", [])),
            keep=tuple(StateCondition.from_dict(item) for item in data.get("keep", [])),
            category=str(data["category"]) if data.get("category") is not None else None,
            required_observations=tuple(copy_json(item) for item in data.get("required_observations", [])),
            expected_finish=copy_json(data.get("expected_finish", {})),
            blueprint_id=str(data["blueprint_id"]) if data.get("blueprint_id") is not None else None,
        )

    def to_dict(self) -> JsonDict:
        """把任务定义转换为 JSON 字典。"""
        result = {
            "user_request": self.user_request,
            "conditions": [item.to_dict() for item in self.conditions],
            "keep": [item.to_dict() for item in self.keep],
        }
        if self.category is not None:
            result["category"] = self.category
        if self.required_observations:
            result["required_observations"] = copy_json(list(self.required_observations))
        if self.expected_finish:
            result["expected_finish"] = copy_json(self.expected_finish)
        if self.blueprint_id is not None:
            result["blueprint_id"] = self.blueprint_id
        return result


@dataclass(frozen=True)
class EpisodeConfig:
    """描述 C 模块的回合数和单回合工具调用上限。"""

    max_turns: int = 10
    max_tool_calls_per_turn: int = 4

    @classmethod
    def from_dict(cls, data: JsonDict) -> "EpisodeConfig":
        """从场景读取 episode 控制参数。"""
        return cls(
            max_turns=int(data.get("max_turns", 10)),
            max_tool_calls_per_turn=int(data.get("max_tool_calls_per_turn", 4)),
        )

    def to_dict(self) -> JsonDict:
        """把 episode 参数转换为字典。"""
        return asdict(self)


@dataclass(frozen=True)
class Scenario:
    """保存一条 V1.2 实验样本的家庭快照、任务和回合配置。"""

    scenario_id: str
    home: Home
    task: TaskSpec
    episode_config: EpisodeConfig
    seed: int | None = None
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict) -> "Scenario":
        """从通过 schema 校验的字典构造场景。"""
        return cls(
            scenario_id=str(data["scenario_id"]),
            home=Home.from_dict(data["home"]),
            task=TaskSpec.from_dict(data["task"]),
            episode_config=EpisodeConfig.from_dict(data.get("episode_config", {})),
            seed=data.get("seed"),
            metadata=copy_json(data.get("metadata", {})),
        )

    def to_dict(self) -> JsonDict:
        """把场景完整转换成可重放的 JSON 字典。"""
        return {
            "scenario_id": self.scenario_id,
            "home": self.home.to_dict(),
            "task": self.task.to_dict(),
            "episode_config": self.episode_config.to_dict(),
            "seed": self.seed,
            "metadata": copy_json(self.metadata),
        }


@dataclass(frozen=True)
class ToolCall:
    """表示 C 从模型响应中提取出的厂商无关工具调用。"""

    name: str
    arguments: JsonDict = field(default_factory=dict)
    call_id: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ToolCall":
        """从字典保留原始字段类型，交给工具 schema 统一返回错误。"""
        if not isinstance(data, dict):
            raise TypeError("tool call must be an object")
        arguments = data.get("arguments", {})
        return cls(
            name=data.get("name", ""),
            arguments=copy_json(arguments),
            call_id=data.get("call_id", data.get("id", "")),
        )

    def to_dict(self) -> JsonDict:
        """输出统一工具调用格式。"""
        return {
            "name": self.name,
            "arguments": copy_json(self.arguments),
            "call_id": self.call_id,
        }


@dataclass(frozen=True)
class AssistantTurn:
    """保存 C 解析后的一次 assistant 决策及原始响应。"""

    tool_calls: tuple[ToolCall, ...] = ()
    text: str = ""
    raw_response: Any = None
    parse_errors: tuple[str, ...] = ()

    def to_dict(self) -> JsonDict:
        """把一次 assistant 决策转换成轨迹字典。"""
        return {
            "tool_calls": [item.to_dict() for item in self.tool_calls],
            "text": self.text,
            "raw_response": copy_json(self.raw_response),
            "parse_errors": list(self.parse_errors),
        }


@dataclass(frozen=True)
class ToolEvent:
    """保存 B 执行单个 ToolCall 的输入、结果和状态差异。"""

    call_id: str
    tool_name: str
    arguments: JsonDict
    result: JsonDict
    state_diff: JsonDict

    @property
    def ok(self) -> bool:
        """返回统一结果外壳中的成功标记。"""
        return bool(self.result.get("ok"))

    @property
    def error_code(self) -> str | None:
        """返回失败时的规范错误码。"""
        error = self.result.get("error")
        return str(error.get("code")) if isinstance(error, dict) and error.get("code") else None

    def to_dict(self) -> JsonDict:
        """把工具事件转换成可审计字典。"""
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": copy_json(self.arguments),
            "result": copy_json(self.result),
            "state_diff": copy_json(self.state_diff),
        }


@dataclass(frozen=True)
class EnvStepResult:
    """保存 B 执行一个规范化工具调用后的返回。"""

    observation: JsonDict
    event: ToolEvent

    def to_dict(self) -> JsonDict:
        """把环境执行结果转换成字典。"""
        return {"observation": copy_json(self.observation), "event": self.event.to_dict()}
