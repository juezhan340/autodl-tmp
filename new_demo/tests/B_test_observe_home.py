"""observe_home 只回房间 id 和名称。"""

from __future__ import annotations

from new_demo.data.D1_home_maker import make_home
from new_demo.env.B_home_env import HomeEnv
from new_demo.env.B_models import ToolCall
from new_demo.tests.C_test_run import _scenario


def test_observe_home_only_room_id_and_name() -> None:
    """返回键只有 rooms；每房只有 room_id 和 display_name。"""
    env = HomeEnv()
    env.reset(_scenario())
    result = env.step(ToolCall("observe_home", {}, "obs"))
    data = result.event.result["data"]
    assert list(data.keys()) == ["rooms"]
    assert data["rooms"]
    for room in data["rooms"]:
        assert set(room.keys()) == {"room_id", "display_name"}
    dumped = str(data)
    assert "environment" not in dumped
    assert "device_count" not in dumped
    assert "room_count" not in dumped
    assert "temperature" not in dumped
    assert "humidity" not in dumped


def test_inspect_room_still_has_environment() -> None:
    """选中房间后仍能读派生温湿度。"""
    env = HomeEnv()
    env.reset(_scenario())
    result = env.step(ToolCall("inspect_room", {"room_id": "room_bedroom"}, "r1"))
    room = result.event.result["data"]["room"]
    assert "environment" in room
    assert "humidity" in room["environment"]


def test_d1_home_observe_is_also_slim() -> None:
    """D1 抽出来的家，observe_home 同样瘦身。"""
    home = make_home(3)
    env = HomeEnv()
    env.reset(_scenario(home=home))
    data = env.step(ToolCall("observe_home", {}, "obs")).event.result["data"]
    assert list(data.keys()) == ["rooms"]
    for room in data["rooms"]:
        assert set(room.keys()) == {"room_id", "display_name"}
