"""D4：复制 s0 打 B，只看 ok/error.code，不走 C.run。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from new_demo.env.B_home_env import HomeEnv
from new_demo.env.B_models import ToolCall, copy_json


FIELD_ACTIONS = {
    "on": None,  # 由 value 决定 turn_on / turn_off
    "target": ("set_temperature", "value"),
    "mode": ("set_mode", "mode"),
    "level": ("set_percentage", "value"),
}
WRITE_OPERATORS = {"eq", "ge", "le"}


@dataclass(frozen=True)
class OracleResult:
    """蓝图可行性结论。失败时没有 blueprint_id。"""

    ok: bool
    error_code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """写成可进 D34_failures 的记录。"""
        return {"ok": self.ok, "error_code": self.error_code, "message": self.message}


def check_blueprint(
    home: dict[str, Any],
    task: dict[str, Any],
    probe: dict[str, Any] | None = None,
) -> OracleResult:
    """复制 s0 启动 B，按类打动作或 inspect。keep 不打。"""
    static = _static_ids(home, task, probe)
    if not static.ok:
        return static
    env = HomeEnv()
    env.reset(_probe_scenario(copy_json(home)))
    snapshot = deepcopy(env.runtime_state)
    outcome = (task.get("expected_finish") or {}).get("outcome")
    if outcome == "refused":
        return _check_refusal(env, snapshot, probe)
    conditions = task.get("conditions") or []
    if conditions:
        return _check_writes(env, conditions)
    return _check_inspects(env, task.get("required_observations") or [])


def _static_ids(
    home: dict[str, Any],
    task: dict[str, Any],
    probe: dict[str, Any] | None,
) -> OracleResult:
    """conditions/keep/required_observations/probe 的 device_id 必须在 s0。"""
    known = {item.get("device_id") for item in home.get("devices", []) if isinstance(item, dict)}
    for group in (task.get("conditions") or [], task.get("keep") or []):
        for item in group:
            device_id = item.get("device_id")
            if device_id not in known:
                return OracleResult(False, "UNKNOWN_DEVICE", f"task references missing device: {device_id}")
    for item in task.get("required_observations") or []:
        if item.get("kind") == "device" and item.get("device_id") not in known:
            return OracleResult(False, "UNKNOWN_DEVICE", f"observation missing device: {item.get('device_id')}")
        if item.get("kind") == "room":
            rooms = {room.get("room_id") for room in home.get("rooms", [])}
            if item.get("room_id") not in rooms:
                return OracleResult(False, "UNKNOWN_ROOM", f"observation missing room: {item.get('room_id')}")
    if probe and probe.get("device_id") not in known:
        return OracleResult(False, "UNKNOWN_DEVICE", f"probe missing device: {probe.get('device_id')}")
    return OracleResult(True)


def _check_writes(env: HomeEnv, conditions: list[dict[str, Any]]) -> OracleResult:
    """每条 condition 必要时打一次 execute_action；ge/le 已成立则不写。"""
    for index, condition in enumerate(conditions):
        call = _call_from_condition(condition, env.runtime_state)
        if isinstance(call, OracleResult):
            return call
        if call is None:
            continue
        result = env.step(call)
        if not result.event.ok:
            code = result.event.error_code or "BAD_REQUEST"
            return OracleResult(False, code, f"condition[{index}] failed: {code}")
    return OracleResult(True)


def _check_refusal(
    env: HomeEnv,
    snapshot: dict[str, Any],
    probe: dict[str, Any] | None,
) -> OracleResult:
    """T4：probe 必须失败，且副本相对 s0 没变。"""
    if not isinstance(probe, dict) or not probe.get("device_id") or not probe.get("action"):
        return OracleResult(False, "BAD_REQUEST", "T4 probe is required")
    call = ToolCall(
        "execute_action",
        {
            "device_id": probe["device_id"],
            "action": probe["action"],
            "params": copy_json(probe.get("params") or {}),
        },
        "d4_probe",
    )
    result = env.step(call)
    if result.event.ok:
        return OracleResult(False, "BAD_REQUEST", "T4 probe must fail")
    if env.runtime_state != snapshot:
        return OracleResult(False, "BAD_REQUEST", "T4 probe mutated state")
    return OracleResult(True)


def _check_inspects(env: HomeEnv, required: list[dict[str, Any]]) -> OracleResult:
    """T5：不 execute，只 inspect；缺 field 则不合格。"""
    if not required:
        return OracleResult(False, "BAD_REQUEST", "query task needs required_observations")
    for index, item in enumerate(required):
        kind = item.get("kind")
        if kind == "device":
            result = env.step(ToolCall("inspect_device", {"device_id": item["device_id"]}, f"d4_obs_{index}"))
            if not result.event.ok:
                return OracleResult(False, result.event.error_code or "UNKNOWN_DEVICE", "inspect_device failed")
            state = result.event.result["data"]["device"]["state"]
            field = item.get("field")
            if field and field not in state:
                return OracleResult(False, "BAD_REQUEST", f"device missing field: {field}")
        elif kind == "room":
            result = env.step(ToolCall("inspect_room", {"room_id": item["room_id"]}, f"d4_obs_{index}"))
            if not result.event.ok:
                return OracleResult(False, result.event.error_code or "UNKNOWN_ROOM", "inspect_room failed")
            environment = result.event.result["data"]["room"].get("environment") or {}
            field = item.get("field")
            if field and field not in environment:
                return OracleResult(False, "BAD_REQUEST", f"room environment missing field: {field}")
        else:
            return OracleResult(False, "BAD_REQUEST", f"unsupported observation kind: {kind}")
    return OracleResult(True)


def _call_from_condition(condition: dict[str, Any], runtime_state: dict[str, Any]) -> ToolCall | OracleResult | None:
    """按 eq/ge/le 译成写入；已满足的 ge/le 返回 None 表示跳过。"""
    device_id = condition.get("device_id")
    field = condition.get("field")
    operator = condition.get("operator", "eq")
    value = condition.get("value", condition.get("equals"))
    if operator not in WRITE_OPERATORS:
        return OracleResult(False, "BAD_REQUEST", f"unsupported write operator: {operator}")
    actual = (runtime_state.get(device_id) or {}).get("state", {}).get(field)
    if operator in {"ge", "le"} and _compare(actual, operator, value):
        return None
    write_value = _write_value(actual, operator, value)
    if field == "on":
        if operator != "eq":
            return OracleResult(False, "BAD_REQUEST", "on condition only supports operator=eq")
        action = "turn_on" if write_value is True else "turn_off" if write_value is False else None
        if action is None:
            return OracleResult(False, "BAD_REQUEST", "on condition value must be boolean")
        return ToolCall("execute_action", {"device_id": device_id, "action": action, "params": {}}, "d4_write")
    mapped = FIELD_ACTIONS.get(field)
    if not mapped:
        return OracleResult(False, "BAD_REQUEST", f"no action mapping for field: {field}")
    action, param = mapped
    return ToolCall(
        "execute_action",
        {"device_id": device_id, "action": action, "params": {param: write_value}},
        "d4_write",
    )


def _write_value(actual: Any, operator: str, value: Any) -> Any:
    """eq 写成目标值；ge/le 尚未成立时写成边界值。"""
    if operator == "eq":
        return value
    return value


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    """与 C-2 同一套比较，供 D4 判断 ge/le 是否已成立。"""
    try:
        if operator == "eq":
            return actual == expected
        if operator == "ge":
            return actual >= expected
        if operator == "le":
            return actual <= expected
    except (TypeError, ValueError):
        return False
    return False


def _probe_scenario(home: dict[str, Any]) -> dict[str, Any]:
    """给 B.reset 用的最小场景，不进入 D5。"""
    return {
        "scenario_id": "d4_probe",
        "blueprint_id": "d4_probe",
        "home": home,
        "user_request": "d4",
        "task": {
            "intent": "d4",
            "conditions": [],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
        "episode_config": {"max_turns": 10, "max_tool_calls_per_turn": 1},
    }
