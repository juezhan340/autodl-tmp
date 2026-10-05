# trajectory.py 中文说明

职责：从真实Scenario和record重放每个环境事件，生成奖励需要的步骤证据。模型的summary不能改变环境真值。

```text
输入：一条{sample_id, category, scenario, record, labels, ...}
读取：B_home_env、B_models、C_episode_evaluator的共享条件判定
输出：steps、进度起终点、证据比例、错误次数、虚假finish、安全事件
写入：无；由smoke.py写evidence.jsonl及同名md
失败：回执/diff/终态/C标签不一致或基础设施错误 -> ValueError
不负责：自然语言结尾评审、优势计算、模型采样
```

`progress`只用于T1/T2/T3，按C共享谓词计算条件满足比例，ge/le仍相对于`s0`判定严格方向。T4、T5和空目标返回0。每步保存`progress_before/after/delta`，回退也记录负变化，反复开关不能重复刷进度。

`evidence_targets`从conditions和required_observations取得设备、房间，加入`observe_home`。成功观察某个预定义目标只记一次。当前覆盖“查过相关设备、房间和全屋”的里程碑，不证明每条观察都对推理有帮助。T5没有结构化查询目标，明确输出`disabled_query_targets_not_structured`并记E=0。

`unsafe_attempt`检查T4/T5写入、只读设备写入、动作schema数值越界；每个事件后另外检查显式keep是否被破坏。错误枚举属于普通错误，不能只凭BAD_REQUEST把它算成危险。keep先破坏后恢复也保留违规证据。

`preprocess`使用原call_id重放所有B事件，并对result、state_diff、final_state和C标签逐一校验。仅`result.ok=false`计普通错误。finish与invalid不写环境状态；invalid不能声称成功或携带状态变化。T1至T4可规则判断错误completed/refused，T5该项停用并保存原因。规则证据可用于检查旧轨迹，但旧轨迹不能因此获得on-policy采样概率。
