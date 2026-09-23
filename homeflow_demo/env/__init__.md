# `homeflow_demo/env/__init__.py` 说明

## 功能

这个文件集中导出 HomeEnv 最常用的接口：`Scenario`、`Action`、`AssistantTurn`、`ToolEvent`、`TurnResult` 和 `HomeEpisodeEnv`。

## 输入输出

```text
输入：homeflow_demo.env.models 与 homeflow_demo.env.home_env
输出：外部模块可以直接导入 Scenario、Action、AssistantTurn、ToolEvent、TurnResult、HomeEpisodeEnv
```

## 使用示例

```python
from homeflow_demo.env import Action, HomeEpisodeEnv, Scenario
```
