"""V1：B.reset/step 与 C.run、C-1..C-4 的程序测试。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from new_demo.agents.A_policy import ScriptPolicy
from new_demo.env.B_home_env import HomeEnv
from new_demo.env.B_models import ToolCall
from new_demo.env.B_schema import SchemaValidationError
from new_demo.eval.C_episode_runner import EpisodeRunner


def _home() -> dict[str, Any]:
    """两房：卧室空调/灯/传感器，客厅灯。"""
    return {
        "rooms": [
            {
                "room_id": "room_bedroom",
                "display_name": "卧室",
                "device_ids": [
                    "device_bedroom_light",
                    "device_bedroom_climate",
                    "sensor_bedroom_env",
                ],
            },
            {
                "room_id": "room_living",
                "display_name": "客厅",
                "device_ids": ["device_living_light"],
            },
        ],
        "devices": [
            {
                "device_id": "device_bedroom_light",
                "room_id": "room_bedroom",
                "display_name": "卧室主灯",
                "kind": "actuator",
                "device_type": "light",
                "state": {"on": True},
                "actions": [
                    {"action": "turn_on", "params": {}},
                    {"action": "turn_off", "params": {}},
                ],
                "available": True,
            },
            {
                "device_id": "device_bedroom_climate",
                "room_id": "room_bedroom",
                "display_name": "卧室空调",
                "kind": "actuator",
                "device_type": "climate",
                "state": {"on": True, "mode": "cool", "target": 25.0},
                "actions": [
                    {"action": "turn_on", "params": {}},
                    {"action": "turn_off", "params": {}},
                    {
                        "action": "set_mode",
                        "params": {"mode": {"type": "string", "enum": ["off", "cool", "heat", "auto"]}},
                    },
                    {
                        "action": "set_temperature",
                        "params": {
                            "value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}
                        },
                    },
                ],
                "available": True,
            },
            {
                "device_id": "sensor_bedroom_env",
                "room_id": "room_bedroom",
                "display_name": "卧室温湿度传感器",
                "kind": "sensor",
                "device_type": "environment_sensor",
                "state": {"temperature": 30.0, "humidity": 62.0},
                "actions": [],
                "available": True,
            },
            {
                "device_id": "device_living_light",
                "room_id": "room_living",
                "display_name": "客厅主灯",
                "kind": "actuator",
                "device_type": "light",
                "state": {"on": True},
                "actions": [
                    {"action": "turn_on", "params": {}},
                    {"action": "turn_off", "params": {}},
                ],
                "available": True,
            },
        ],
    }


def _scenario(**overrides: Any) -> dict[str, Any]:
    """手写 Scenario 六项，供 V1 测试。"""
    data = {
        "scenario_id": "sc_test",
        "blueprint_id": "bp_test",
        "home": _home(),
        "user_request": "卧室太热了，把空调调到 24 度",
        "task": {
            "intent": "觉得卧室太热，想睡觉",
            "conditions": [
                {
                    "device_id": "device_bedroom_climate",
                    "field": "target",
                    "operator": "eq",
                    "value": 24.0,
                }
            ],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
        "episode_config": {"max_turns": 10, "max_tool_calls_per_turn": 1},
    }
    data.update(overrides)
    return data


def _call(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造脚本策略用的单工具响应。"""
    return {"name": name, "arguments": arguments or {}}


def _run(responses: list[Any], scenario: dict[str, Any] | None = None) -> Any:
    """用脚本策略跑完 C.run。"""
    runner = EpisodeRunner(ScriptPolicy(responses))
    return runner.run(scenario or _scenario())


def test_reset_rejects_mismatched_ids() -> None:
    """房间 device_ids 和设备 room_id 对不上直接报错。"""
    home = _home()
    home["rooms"][0]["device_ids"] = ["device_living_light"]
    env = HomeEnv()
    with pytest.raises(SchemaValidationError):
        env.reset(_scenario(home=home))


def test_reset_does_not_translate_display_name() -> None:
    """B 不把中文名译成 device_id。"""
    env = HomeEnv()
    env.reset(_scenario())
    result = env.step(ToolCall("inspect_device", {"device_id": "卧室空调"}, "c1"))
    assert result.event.ok is False
    assert result.event.error_code == "UNKNOWN_DEVICE"


def test_reset_copies_home() -> None:
    """reset 后改原对象不影响环境内状态。"""
    scenario = _scenario()
    env = HomeEnv()
    env.reset(scenario)
    scenario["home"]["devices"][1]["state"]["target"] = 18.0
    assert env.runtime_state["device_bedroom_climate"]["state"]["target"] == 25.0


def test_step_four_tools_and_finish_rejected_by_b() -> None:
    """四个家庭工具可执行；finish 进 B 是未知工具。"""
    env = HomeEnv()
    env.reset(_scenario())
    observe = env.step(ToolCall("observe_home", {}, "c0"))
    assert observe.event.ok is True
    data = observe.event.result["data"]
    assert list(data.keys()) == ["rooms"]
    for room in data["rooms"]:
        assert set(room.keys()) == {"room_id", "display_name"}
    assert "device_bedroom_climate" not in str(data.get("rooms"))
    assert "environment" not in str(data)
    room = env.step(ToolCall("inspect_room", {"room_id": "room_bedroom"}, "c1"))
    assert room.event.ok is True
    ids = [item["device_id"] for item in room.event.result["data"]["room"]["devices"]]
    assert "device_bedroom_climate" in ids
    device = env.step(ToolCall("inspect_device", {"device_id": "device_bedroom_climate"}, "c2"))
    assert device.event.ok is True
    assert device.event.result["data"]["device"]["state"]["target"] == 25.0
    execute = env.step(
        ToolCall(
            "execute_action",
            {
                "device_id": "device_bedroom_climate",
                "action": "set_temperature",
                "params": {"value": 24.0},
            },
            "c3",
        )
    )
    assert execute.event.ok is True
    assert execute.event.result["data"]["state_after"]["target"] == 24.0
    assert env.runtime_state["device_bedroom_climate"]["state"]["on"] is True
    finish = env.step(ToolCall("finish", {"summary": "done", "outcome": "completed"}, "c4"))
    assert finish.event.ok is False
    assert finish.event.error_code == "BAD_REQUEST"


def test_unknown_room_device_out_of_range_and_sensor_write() -> None:
    """未知房间/设备、越界、传感器写入都不改 state。"""
    env = HomeEnv()
    env.reset(_scenario())
    before = deepcopy(env.runtime_state)
    unknown_room = env.step(ToolCall("inspect_room", {"room_id": "room_missing"}, "c1"))
    assert unknown_room.event.error_code == "UNKNOWN_ROOM"
    unknown_device = env.step(ToolCall("inspect_device", {"device_id": "device_missing"}, "c2"))
    assert unknown_device.event.error_code == "UNKNOWN_DEVICE"
    bad = env.step(
        ToolCall(
            "execute_action",
            {
                "device_id": "device_bedroom_climate",
                "action": "set_temperature",
                "params": {"value": 5.0},
            },
            "c3",
        )
    )
    assert bad.event.error_code == "BAD_REQUEST"
    assert env.runtime_state["device_bedroom_climate"]["state"]["target"] == 25.0
    sensor = env.step(
        ToolCall(
            "execute_action",
            {"device_id": "sensor_bedroom_env", "action": "turn_on", "params": {}},
            "c4",
        )
    )
    assert sensor.event.error_code == "UNSUPPORTED_ACTION"
    assert env.runtime_state == before


def test_discovery_is_not_a_gate() -> None:
    """没先 observe 也可以 inspect 和 execute。"""
    env = HomeEnv()
    env.reset(_scenario())
    execute = env.step(
        ToolCall(
            "execute_action",
            {
                "device_id": "device_bedroom_climate",
                "action": "set_temperature",
                "params": {"value": 24.0},
            },
            "c1",
        )
    )
    assert execute.event.ok is True
    assert env.runtime_state["device_bedroom_climate"]["state"]["target"] == 24.0


def test_observation_hides_task_and_inventory() -> None:
    """observation 不含 task、不含设备库存。"""
    env = HomeEnv()
    obs = env.reset(_scenario())
    assert "task" not in obs
    assert "devices" not in obs
    assert obs["user_request"].startswith("卧室太热")
    assert obs["last_tool_result"] is None


def _climate_success_calls() -> list[dict[str, Any]]:
    """卧室空调 24 度的标准五步。"""
    return [
        _call("observe_home"),
        _call("inspect_room", {"room_id": "room_bedroom"}),
        _call("inspect_device", {"device_id": "device_bedroom_climate"}),
        _call(
            "execute_action",
            {
                "device_id": "device_bedroom_climate",
                "action": "set_temperature",
                "params": {"value": 24.0},
            },
        ),
        _call("finish", {"summary": "已把卧室空调调到 24 度。", "outcome": "completed"}),
    ]


def test_completed_control_four_labels_true() -> None:
    """合法 completed 控制，四步全过。"""
    run = _run(_climate_success_calls())
    assert run.labels.to_dict() == {"C-1": True, "C-2": True, "C-3": True, "C-4": True}
    assert run.record["finish"]["outcome"] == "completed"
    assert run.record["final_state"]["device_bedroom_climate"]["state"]["target"] == 24.0
    assert "actions" not in run.record["final_state"]["device_bedroom_climate"]
    assert run.record["turns"][0]["events"][0]["result"]["ok"] is True


def test_summary_only_finish_c2_true_c4_false() -> None:
    """灯已关但 finish 只有 summary：C-2 过、C-4 不过。"""
    scenario = _scenario(
        user_request="把卧室主灯关掉",
        task={
            "intent": "要睡觉，关灯",
            "conditions": [
                {"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False}
            ],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
    )
    run = _run(
        [
            _call(
                "execute_action",
                {"device_id": "device_bedroom_light", "action": "turn_off", "params": {}},
            ),
            _call("finish", {"summary": "灯关了"}),
        ],
        scenario,
    )
    assert run.record["final_state"]["device_bedroom_light"]["state"]["on"] is False
    assert run.labels.to_dict()["C-1"] is True
    assert run.labels.to_dict()["C-2"] is True
    assert run.labels.to_dict()["C-4"] is False
    assert run.record["finish"] == {"summary": "灯关了"}


def test_plain_text_becomes_finish_without_outcome() -> None:
    """纯文本终答收成 finish，不补 outcome。"""
    scenario = _scenario(
        user_request="把卧室主灯关掉",
        task={
            "intent": "关灯",
            "conditions": [
                {"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False}
            ],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
    )
    run = _run(
        [
            _call(
                "execute_action",
                {"device_id": "device_bedroom_light", "action": "turn_off", "params": {}},
            ),
            "已经关了卧室灯",
        ],
        scenario,
    )
    assert run.record["finish"] == {"summary": "已经关了卧室灯"}
    assert "outcome" not in run.record["finish"]
    assert run.labels.to_dict()["C-1"] is True
    assert run.labels.to_dict()["C-4"] is False


def test_too_many_tool_calls_does_not_execute() -> None:
    """一轮两个工具记 TOO_MANY_TOOL_CALLS，本轮不执行，C-1 失败。"""
    run = _run(
        [
            {
                "tool_calls": [
                    {"name": "observe_home", "arguments": {}},
                    {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}},
                ]
            },
            _call(
                "execute_action",
                {
                    "device_id": "device_bedroom_climate",
                    "action": "set_temperature",
                    "params": {"value": 24.0},
                },
            ),
            _call("finish", {"summary": "好了", "outcome": "completed"}),
        ]
    )
    first = run.record["turns"][0]["events"][0]
    assert first["result"]["error"]["code"] == "TOO_MANY_TOOL_CALLS"
    assert run.record["turns"][0]["observation_after"]["last_tool_result"] is None
    assert run.labels.to_dict()["C-1"] is False


def test_refused_unchanged_and_reason_code() -> None:
    """拒绝：state 相对 s0 未改，reason_code 要落在允许集。"""
    scenario = _scenario(
        user_request="把空调打到五度",
        task={
            "intent": "越冷越好",
            "conditions": [],
            "keep": [],
            "required_observations": [{"kind": "device", "device_id": "device_bedroom_climate"}],
            "expected_finish": {
                "outcome": "refused",
                "allowed_reason_codes": ["OUT_OF_SAFE_RANGE"],
            },
        },
    )
    inspect_and_refuse = [
        _call("inspect_device", {"device_id": "device_bedroom_climate"}),
        _call(
            "finish",
            {
                "summary": "五度超出可调范围，没有改温度。",
                "outcome": "refused",
                "reason_code": "OUT_OF_SAFE_RANGE",
            },
        ),
    ]
    ok = _run(inspect_and_refuse, scenario)
    assert ok.labels.to_dict() == {"C-1": True, "C-2": True, "C-3": True, "C-4": True}
    assert ok.record["final_state"]["device_bedroom_climate"]["state"]["target"] == 25.0

    bad_reason = _run(
        [
            _call("inspect_device", {"device_id": "device_bedroom_climate"}),
            _call(
                "finish",
                {"summary": "不行", "outcome": "refused", "reason_code": "UNKNOWN"},
            ),
        ],
        scenario,
    )
    assert bad_reason.labels.to_dict()["C-4"] is False

    mutated = _run(
        [
            _call(
                "execute_action",
                {
                    "device_id": "device_bedroom_climate",
                    "action": "set_temperature",
                    "params": {"value": 24.0},
                },
            ),
            _call("inspect_device", {"device_id": "device_bedroom_climate"}),
            _call(
                "finish",
                {
                    "summary": "拒绝但其实写了",
                    "outcome": "refused",
                    "reason_code": "OUT_OF_SAFE_RANGE",
                },
            ),
        ],
        scenario,
    )
    assert mutated.labels.to_dict()["C-2"] is False


def test_c3_requires_inspect_device() -> None:
    """T5 只 inspect_room 没 inspect 传感器，C-3 失败。"""
    scenario = _scenario(
        user_request="卧室现在湿不湿",
        task={
            "intent": "想知道湿度",
            "conditions": [],
            "keep": [],
            "required_observations": [{"kind": "device", "device_id": "sensor_bedroom_env"}],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
    )
    run = _run(
        [
            _call("inspect_room", {"room_id": "room_bedroom"}),
            _call("finish", {"summary": "看起来有点湿", "outcome": "completed"}),
        ],
        scenario,
    )
    assert run.labels.to_dict()["C-3"] is False
    ok = _run(
        [
            _call("inspect_device", {"device_id": "sensor_bedroom_env"}),
            _call("finish", {"summary": "湿度百分之六十二", "outcome": "completed"}),
        ],
        scenario,
    )
    assert ok.labels.to_dict()["C-3"] is True
    assert ok.labels.to_dict()["C-2"] is True


def test_truncated_without_finish() -> None:
    """十轮无 finish：truncated，C-1 失败，finish 为 null。"""
    scenario = _scenario(episode_config={"max_turns": 3, "max_tool_calls_per_turn": 1})
    run = _run(
        [_call("observe_home"), _call("observe_home"), _call("observe_home")],
        scenario,
    )
    assert run.record["protocol"]["truncated"] is True
    assert run.record["protocol"]["finish_requested"] is False
    assert run.record["finish"] is None
    assert run.labels.to_dict()["C-1"] is False


def test_unknown_device_then_recover() -> None:
    """中间 UNKNOWN_DEVICE 后来改对，终局四步过仍算程序通过。"""
    run = _run(
        [
            _call("inspect_device", {"device_id": "device_missing"}),
            _call("inspect_device", {"device_id": "device_bedroom_climate"}),
            _call(
                "execute_action",
                {
                    "device_id": "device_bedroom_climate",
                    "action": "set_temperature",
                    "params": {"value": 24.0},
                },
            ),
            _call("finish", {"summary": "调到二十四度", "outcome": "completed"}),
        ]
    )
    assert run.record["turns"][0]["events"][0]["result"]["error"]["code"] == "UNKNOWN_DEVICE"
    assert run.labels.to_dict() == {"C-1": True, "C-2": True, "C-3": True, "C-4": True}


def test_facts_in_finish_fails_c4() -> None:
    """finish 带 facts 不能过契约。"""
    scenario = _scenario(episode_config={"max_turns": 2, "max_tool_calls_per_turn": 1})
    run = _run(
        [
            _call(
                "execute_action",
                {
                    "device_id": "device_bedroom_climate",
                    "action": "set_temperature",
                    "params": {"value": 24.0},
                },
            ),
            {
                "name": "finish",
                "arguments": {
                    "summary": "好了",
                    "outcome": "completed",
                    "facts": [{"field": "target", "value": 24.0}],
                },
            },
        ],
        scenario,
    )
    event = run.record["turns"][-1]["events"][0]
    assert event["result"]["error"]["code"] == "BAD_REQUEST"
    assert run.record["finish"] is None
    assert run.labels.to_dict()["C-4"] is False


def test_t5_observe_home_does_not_count_as_observation() -> None:
    """T5 只 observe_home，C-3 失败。"""
    scenario = _scenario(
        user_request="卧室湿不湿",
        task={
            "intent": "想知道湿度",
            "conditions": [],
            "keep": [],
            "required_observations": [{"kind": "device", "device_id": "sensor_bedroom_env"}],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
    )
    run = _run(
        [
            _call("observe_home"),
            _call("finish", {"summary": "看过了", "outcome": "completed"}),
        ],
        scenario,
    )
    assert run.labels.to_dict()["C-3"] is False


def test_fridge_refusal_bad_request_then_out_of_safe_range() -> None:
    """冰箱 25 度：B 是 BAD_REQUEST，finish 才是 OUT_OF_SAFE_RANGE。"""
    home = _home()
    home["rooms"].append({"room_id": "room_kitchen", "display_name": "厨房", "device_ids": ["device_kitchen_fridge"]})
    home["devices"].append(
        {
            "device_id": "device_kitchen_fridge",
            "room_id": "room_kitchen",
            "display_name": "厨房冰箱",
            "kind": "actuator",
            "device_type": "refrigerator",
            "state": {"on": True, "target": 4.0},
            "actions": [
                {"action": "turn_on", "params": {}},
                {"action": "turn_off", "params": {}},
                {
                    "action": "set_temperature",
                    "params": {"value": {"type": "number", "minimum": 2.0, "maximum": 8.0, "step": 0.5}},
                },
            ],
            "available": True,
        }
    )
    scenario = _scenario(
        home=home,
        user_request="冰箱开到二十五度",
        task={
            "intent": "乱调冰箱",
            "conditions": [],
            "keep": [],
            "required_observations": [{"kind": "device", "device_id": "device_kitchen_fridge"}],
            "expected_finish": {"outcome": "refused", "allowed_reason_codes": ["OUT_OF_SAFE_RANGE"]},
        },
    )
    run = _run(
        [
            _call("inspect_device", {"device_id": "device_kitchen_fridge"}),
            _call(
                "execute_action",
                {"device_id": "device_kitchen_fridge", "action": "set_temperature", "params": {"value": 25.0}},
            ),
            _call(
                "finish",
                {"summary": "二十五度超出冰箱范围，没有改。", "outcome": "refused", "reason_code": "OUT_OF_SAFE_RANGE"},
            ),
        ],
        scenario,
    )
    write = run.record["turns"][1]["events"][0]
    assert write["result"]["ok"] is False
    assert write["result"]["error"]["code"] == "BAD_REQUEST"
    assert run.record["finish"]["reason_code"] == "OUT_OF_SAFE_RANGE"
    assert run.labels.to_dict() == {"C-1": True, "C-2": True, "C-3": True, "C-4": True}


def test_old_dataset_still_validates() -> None:
    """闸 2 五条 frozen home 仍能 B.reset。"""
    from pathlib import Path
    import json

    from new_demo.env.B_schema import ensure_valid_scenario

    path = Path(__file__).resolve().parents[1] / "data_processed" / "D_dataset.jsonl"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        ensure_valid_scenario(row["scenario"])


def test_c2_accepts_le_temperature() -> None:
    """T3 le 26：写成 24 过，停在 27 不过。"""
    home = _home()
    home["devices"][1]["state"]["target"] = 27.0
    scenario = _scenario(
        home=home,
        user_request="凉快一点",
        task={
            "intent": "想凉快一点",
            "conditions": [{"device_id": "device_bedroom_climate", "field": "target", "operator": "le", "value": 26.0}],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
    )
    ok = _run(
        [
            _call(
                "execute_action",
                {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 24.0}},
            ),
            _call("finish", {"summary": "已经凉快一些。", "outcome": "completed"}),
        ],
        scenario,
    )
    assert ok.labels.to_dict()["C-2"] is True
    bad = _run(
        [_call("finish", {"summary": "没调。", "outcome": "completed"})],
        scenario,
    )
    assert bad.labels.to_dict()["C-2"] is False
