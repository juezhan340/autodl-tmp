# HomeFlow 简练 Demo 完整实施方案

> 方案日期：2026-09-21  
> 目标：用一个规模受控但闭环完整的 Demo，验证 HomeEnv、DeepSeek 轨迹合成、SFT、LoRA-GRPO 和独立测评。  
> 本机：单张 NVIDIA GeForce RTX 4090，24GB 显存，系统内存约 1TiB。  
> 训练主线：Qwen2.5-1.5B-Instruct Transformers 权重 + PEFT LoRA + TRL。  
> 教师模型：DeepSeek API 只生成候选轨迹，不负责最终环境裁判。

## 先看整体方案

```text
第一部分：HomeEnv
  确定性家庭状态机 + 工具校验 + 目标谓词 + reward verifier

第二部分：数据与测评
  程序生成场景
      -> DeepSeek 生成候选轨迹
      -> HomeEnv 执行和筛选
      -> 成功轨迹进入 SFT
      -> 独立场景进入 eval

第三部分：强化学习
  Qwen2.5-1.5B LoRA-SFT
      -> HomeEnv 在线 rollout
      -> 同一任务采样多条轨迹
      -> 环境 reward 形成组相对优势
      -> LoRA-GRPO 更新
```

```text
场景生成器
      |
      +--> train scenarios --> DeepSeek --> HomeEnv verifier --> SFT data
      |
      +--> validation scenarios ------------------------------+
      |                                                       |
      +--> frozen eval scenarios --> model rollout --> HomeEnv |
                                                              |
Qwen2.5-1.5B-Instruct -> LoRA-SFT -> LoRA-GRPO --------------+
```

Demo 第一版明确不做：MCTS、`pyexec`、真实 Home Assistant、多卡、vLLM 并行、复杂用户模拟器、连续物理仿真。目标是先验证：

```text
环境能判定
数据能生成
模型能学会工具调用
RL 能获得非零优势信号
测评能重复
```

当前 V1 的 `HomeEpisodeEnv.step(Action)` 是原子工具动作级接口，主要用于状态机、规则 Oracle 和环境裁判验收。接入 DeepSeek、SFT 和在线 RL 之前，必须先完成 V1.1 的 turn-level 修订：一次模型 assistant 输出对应一次环境 step，turn 内工具调用由环境内部执行并汇总。

## 1. 研究问题与实验边界

### 1.1 核心研究问题

```text
在固定 HomeEnv 和固定工具协议下，
DeepSeek 验证轨迹 + LoRA-SFT + HomeEnv reward 的 LoRA-GRPO，
能否提高 1.5B 模型的智能家居任务成功率？
```

至少保留四个比较对象：

```text
Base：   Qwen2.5-1.5B-Instruct 原始模型
SFT：    成功轨迹上的 LoRA-SFT checkpoint
RL：     SFT checkpoint 上继续做 HomeEnv LoRA-GRPO
Oracle： 程序规划器或 DeepSeek 成功轨迹的环境执行结果
```

### 1.2 第一版任务范围

```text
T1 单设备控制：   打开/关闭灯、设置亮度、调整温度
T2 多设备控制：   完成两个或三个设备目标
T3 查询后控制：   先查询状态，再决定是否控制
T4 条件任务：     满足条件时执行控制，否则结束
T5 澄清任务：     缺少设备或参数时请求补充信息
```

设备类型限制为四类：

```text
light：       power、brightness、color_temp
thermostat：  power、temperature、mode
switch：      power
lock：        locked
```

每个家庭只放 4～8 个设备，覆盖 2～4 个房间。设备 ID 使用稳定字符串，例如：

```text
living_room.main_light
bedroom.air_conditioner
kitchen.coffee_switch
front_door.lock
```

## 2. 推荐目录与模块边界

第一版单独创建 `homeflow_demo/`，不把训练代码塞进 MiniMind，也不把 HomeEnv 绑定到现有 Web/API 服务。

```text
/root/autodl-tmp/homeflow_demo/
├── env/
│   ├── models.py              # 场景、状态、动作、结果数据结构
│   ├── state_engine.py        # 状态转移和设备约束
│   ├── predicates.py          # 完成度和终局判定
│   ├── home_env.py            # HomeEpisodeEnv 核心
│   ├── tool_schema.py         # 工具定义和参数校验
│   └── gym_adapter.py         # 可选 Gymnasium 薄适配器
├── data/
│   ├── scenario_generator.py  # 训练/验证/测试场景生成
│   ├── deepseek_teacher.py    # DeepSeek API 候选轨迹生成
│   ├── trajectory_verifier.py # HomeEnv 执行、筛选、去重
│   ├── planner.py             # 程序规划器兜底
│   └── dataset_builder.py     # SFT、RL、评测文件构造
├── train/
│   ├── sft.py                 # TRL + PEFT LoRA SFT
│   ├── grpo.py                # HomeEnv rollout + LoRA-GRPO
│   └── configs/demo.yaml      # 统一实验配置
├── eval/
│   ├── run_eval.py            # 独立环境测评
│   ├── metrics.py             # 指标计算
│   └── report.py              # JSON 和 Markdown 报告
├── data_raw/                  # API 原始响应
├── data_processed/            # HomeEnv 验证后的数据
├── checkpoints/               # SFT/RL adapter
└── README.md                  # 运行顺序、输入输出和验收条件
```

职责边界固定为：

```text
HomeEnv：       判断动作、状态变化、目标完成和 reward
DeepSeek：      生成候选用户表达、工具调用和自然语言回复
SFT：           学习合法工具格式和基本成功策略
GRPO：          比较同一任务下多条在线轨迹的环境回报
评测：          只调用模型和 HomeEnv，不读取教师标准轨迹
```

每个后续代码文件都要配套同名中文 `.md`，说明输入、输出、调用顺序和失败返回。

# 第一部分 HomeEnv 本身的设计

## 3. HomeEnv 的最小数据结构

场景是一个 episode 的只读输入，运行状态由环境内部维护。

```json
{
  "scenario_id": "train_t2_000031",
  "seed": 31,
  "user_request": "睡前关闭卧室的灯，并把空调设置为26度。",
  "devices": [
    {
      "id": "bedroom.light",
      "type": "light",
      "room": "bedroom",
      "state": {"power": "on", "brightness": 80}
    },
    {
      "id": "bedroom.air_conditioner",
      "type": "thermostat",
      "room": "bedroom",
      "state": {"power": "on", "temperature": 24, "mode": "cool"}
    }
  ],
  "goal": {
    "predicates": [
      {"device_id": "bedroom.light", "field": "power", "equals": "off"},
      {"device_id": "bedroom.air_conditioner", "field": "temperature", "equals": 26}
    ]
  },
  "max_steps": 6
}
```

模型输出统一解析成结构化动作：

```json
{
  "name": "control_device",
  "arguments": {
    "device_id": "bedroom.light",
    "command": "set_power",
    "value": "off"
  }
}
```

环境不执行任意 Python 或未经校验的字符串。

## 4. HomeEpisodeEnv 接口

```python
class HomeEpisodeEnv:
    def reset(self, scenario, seed=None): ...
    def step(self, assistant_turn): ...
    def snapshot(self): ...
    def restore(self, snapshot): ...
    def fork(self): ...
    def trajectory(self): ...
    def final_result(self): ...
```

接口语义：

```text
reset：       加载场景并恢复初始设备状态
step：        消费一次 assistant turn，执行其中工具调用并计算 turn reward
snapshot：    保存当前状态，便于调试和搜索
restore：     恢复指定状态
fork：        复制当前 episode，避免 rollout 互相污染
trajectory：  返回完整 turn、tool_events、观察、reward 和状态差异
final_result：返回 success、完成度、失败原因和最终状态
```

`fork()` 对 GRPO 必须存在。同一任务生成 2～4 条轨迹时，每条轨迹都从相同初始状态独立开始。

环境内部保留原子执行原语 `_apply_action(action)`。它负责单个工具的校验和状态变化；公开的 `step(assistant_turn)` 负责将一个模型输出中的一个或多个工具调用聚合为一条策略 transition。

## 5. 模型可见工具

第一版只提供三个工具：

```text
query_device(device_id, fields)
  读取指定设备的公开状态。

control_device(device_id, command, value)
  修改设备状态，参数必须满足设备类型约束。

finish(summary)
  声明任务结束，由环境再次检查目标谓词。
```

`ask_user` 作为第二阶段能力保留。第一版澄清任务先让环境返回 `needs_clarification=true`，模型生成询问文本后结束当前 episode，不实现真正的用户模拟循环。

## 6. 状态转移与参数约束

```text
合法动作：
  设备存在
  工具名存在
  参数类型正确
  参数在允许范围
  command 与设备类型匹配

非法动作：
  不修改设备状态
  写入稳定 error_code
  增加非法动作计数
  返回负奖励
```

第一版约束：

```text
light.set_power       value ∈ {on, off}
light.set_brightness  value ∈ [0, 100]
thermostat.set_temp   value ∈ [16, 30]
thermostat.set_mode   value ∈ {cool, heat, auto, off}
lock.set_locked       value ∈ {true, false}
```

状态转移必须确定：

```text
相同 scenario + 相同 seed + 相同 action sequence
                    |
                    v
      相同最终状态、相同 reward、相同失败原因
```

## 7. Observation、目标谓词和 reward

初始 observation 只包含模型需要的信息：

```text
用户请求
可用设备摘要
可用工具 schema
当前对话上下文
```

工具成功返回：

```json
{
  "ok": true,
  "device_id": "bedroom.light",
  "changed": {"power": {"from": "on", "to": "off"}},
  "current_state": {"power": "off", "brightness": 80}
}
```

工具失败返回：

```json
{
  "ok": false,
  "error_code": "VALUE_OUT_OF_RANGE",
  "message": "temperature must be between 16 and 30"
}
```

完成度使用目标谓词满足比例。对模型训练而言，完成度在一个 turn 的全部工具调用执行前后各计算一次：

```text
completion_before = turn 开始前已满足谓词数量 / 总谓词数量
completion_after  = turn 执行后已满足谓词数量 / 总谓词数量
```

第一版 reward：

```text
r_progress = completion_after - completion_before
r_valid    = +0.02       合法且产生有效状态变化
r_query    = 0           合法查询不直接给完成奖励
r_invalid  = -0.30       工具、设备或参数错误
r_repeat   = -0.10       无状态变化的重复动作
r_finish   = +1.00       finish 且全部目标满足
r_fail     = -0.50       提前 finish 或超步数仍未完成
r_turn     = -0.01       每个 assistant turn 轻微成本
```

```text
R_episode = clip(
    2.0 * sum(r_progress)
    + sum(r_valid + r_invalid + r_repeat + r_turn)
    + r_finish_or_fail,
    -1.0,
    2.0
)
```

第一版不加入语言模型 judge reward，否则环境真值、DeepSeek 偏好和 judge 偏好会混在一起。

## 8. 终止条件与 Gym 适配

```text
terminated=True：
  finish 成功
  finish 失败
  环境判定任务不可完成

truncated=True：
  达到 max_turns
  生成达到 max_new_tokens
  工具解析连续失败超过阈值
```

核心环境不强制继承 Gymnasium，但提供薄适配器：

```text
HomeEpisodeEnv.reset() -> GymHomeEnvAdapter.reset()
HomeEpisodeEnv.step(assistant_turn) -> GymHomeEnvAdapter.step(assistant_turn)
snapshot / fork / trajectory -> 数据生成器和 RL adapter 使用
```

兼容期间可以继续读取场景字段 `max_steps`，但 V1.1 内部统一解释为 `max_turns`。另外单独配置 `max_tool_calls_per_turn`，避免把工具调用数量混入模型决策步数。

# 第二部分 训练数据与测评数据合成路线

## 9. 数据角色分工

```text
规则场景生成器：  保证状态、任务和目标谓词结构正确
程序规划器：      保证 feasible 场景至少有一条成功轨迹
DeepSeek API：     生成自然语言和候选工具轨迹
HomeEnv：          执行轨迹、判断成功、生成 reward 真值
```

DeepSeek 是教师和候选策略，不是裁判。任何进入 SFT 的轨迹都必须经过 HomeEnv 完整执行。

## 10. 场景生成

先程序生成结构化场景，再让 DeepSeek 负责语言化和候选轨迹生成：

```text
设备模板
  -> 随机初始状态
  -> 任务模板和目标谓词
  -> 可行性检查
  -> 用户请求自然语言化
  -> 候选轨迹生成
```

任务模板：

```text
单目标：把 {room} 的 {device} {command}。
多目标：睡前完成 {goal_a}，并完成 {goal_b}。
查询控制：如果 {device} 当前开启，则将其关闭。
条件任务：只有当 {device} 温度高于 {value} 时才调整。
澄清任务：把空调调到合适温度，但不提供具体温度。
```

每个 feasible 场景必须经过有限步搜索或程序规划器检查：

```text
初始状态 + 合法动作集合
       |
       v
是否存在有限步序列满足全部目标谓词？
       |
       +--> 是：进入 feasible 集
       +--> 否：进入 clarification/impossible 集
```

## 11. 数据划分

第一轮建议规模：

```text
训练场景：  80
验证场景：  20
测评场景：  40
```

第二轮可报告规模：

```text
训练场景：  240
验证场景：  60
测评场景：  100
```

不能只按随机 seed 切分。划分键至少包含：

```text
scenario_template_id
device_combination_id
goal_composition_id
paraphrase_group_id
```

推荐拆分：

```text
训练集：  主要设备组合和任务模板
验证集：  部分未见设备组合或目标组合
测评集：  未见 seed、未见组合、未见语言改写
```

同一 `paraphrase_group_id` 不能跨 train/val/eval，否则只是换表面措辞，测评会偏乐观。

## 12. DeepSeek API 合成候选轨迹

输入包含：

```text
结构化家庭状态摘要
用户请求
设备和工具 schema
最大工具调用轮数
JSON 输出格式约束
```

输出只允许结构化 JSON，不要求或保存隐藏推理：

```json
{
  "assistant_turns": [
    {
      "tool_call": {
        "name": "control_device",
        "arguments": {
          "device_id": "bedroom.light",
          "command": "set_power",
          "value": "off"
        }
      }
    },
    {
      "tool_call": {
        "name": "finish",
        "arguments": {"summary": "任务已完成。"}
      }
    }
  ]
}
```

建议参数：

```text
每个场景候选数：  3～5 条
temperature：     0.4～0.8
最大工具调用：    6
API 失败重试：     3 次
格式失败重试：     1～2 次
```

API 原始数据单独落盘：

```text
scenario_id
request_id
model_name
prompt_version
raw_response
parsed_response
timestamp
error
```

密钥只从环境变量读取：

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_MODEL
```

不把 key 写入 JSONL、配置、日志或 Git。

## 13. HomeEnv 执行、验证和筛选

```text
解析 JSON
  -> 校验工具名
  -> 校验参数 schema
  -> HomeEnv.reset(scenario)
  -> 逐步执行 tool_call
  -> 记录 observation、state diff、reward
  -> 检查 finish 和目标谓词
  -> 计算质量分
  -> 成功轨迹去重并落盘
```

轨迹质量只取环境事实：

```text
success
  + 完成步数更少
  + 非法动作更少
  + 无效查询更少
  + 状态变化更直接
```

筛选规则：

```text
成功且合法：       进入 SFT 候选池
成功但步骤冗余：   每个场景最多保留 1 条多样性样本
失败但格式正确：   进入 hard negative 池
非法或无法解析：   只用于错误统计，不进入成功 SFT
```

## 14. 程序规划器兜底

不能依赖 DeepSeek 一定生成成功轨迹。第一版写一个有限设备、有限谓词的规则规划器：

```text
目标谓词
  -> 反查设备和字段
  -> 生成 control_device 序列
  -> HomeEnv 执行
  -> 成功后转换为标准 messages/tool_calls/tool_response
```

规划器不追求通用智能，职责只有三个：

```text
每个 feasible 场景至少有一条成功轨迹
为 DeepSeek 轨迹提供质量对照
避免 API 偶发失败导致 SFT 数据断供
```

## 15. SFT 数据格式

验证成功后转换成 Qwen chat template 可消费的消息格式：

```json
{
  "scenario_id": "train_t2_000031",
  "messages": [
    {"role": "system", "content": "你是智能家居助手。"},
    {"role": "user", "content": "关闭卧室的灯。"},
    {"role": "assistant", "tool_calls": [{"name": "control_device", "arguments": {"device_id": "bedroom.light", "command": "set_power", "value": "off"}}]},
    {"role": "tool", "content": "{\"ok\":true,\"changed\":{\"power\":{\"from\":\"on\",\"to\":\"off\"}}}"},
    {"role": "assistant", "tool_calls": [{"name": "finish", "arguments": {"summary": "任务已完成。"}}]}
  ],
  "env_result": {"success": true, "completion": 1.0, "steps": 2}
}
```

`env_result` 只用于审计和统计，不拼进模型输入。第一版 SFT 只使用成功轨迹；失败轨迹暂存，后续再做 hard negative 或拒答训练消融。

## 16. 测评数据格式

测评文件只给场景和用户任务，不给教师标准轨迹：

```json
{
  "scenario_id": "eval_unseen_0007",
  "seed": 7007,
  "messages": [
    {"role": "system", "content": "你是智能家居助手。"},
    {"role": "user", "content": "如果客厅空调正在制冷，就把温度调整到25度。"}
  ],
  "scenario": {
    "devices": [
      {
        "id": "living_room.air_conditioner",
        "type": "thermostat",
        "room": "living_room",
        "state": {"power": "on", "temperature": 28, "mode": "cool"}
      }
    ],
    "goal": {
      "predicates": [
        {"device_id": "living_room.air_conditioner", "field": "temperature", "equals": 25}
      ]
    },
    "max_steps": 4
  },
  "split": "eval"
}
```

评测时由 `scenario` 重建 HomeEnv，模型自主交互。目标谓词只给评测器，不拼进模型 prompt。

# 第三部分 强化学习方案设计

## 17. 训练阶段顺序

```text
阶段 A：HomeEnv 单元测试和规则轨迹验证
阶段 B：DeepSeek + 程序规划器合成成功轨迹
阶段 C：Qwen2.5-1.5B LoRA-SFT
阶段 D：HomeEnv 在线 rollout + LoRA-GRPO
阶段 E：冻结 eval 集测评和消融实验
```

不能跳过 SFT 直接做 RL。未经工具格式对齐的 1.5B 模型可能几乎不产生合法 tool call，使同组 reward 全部相同，GRPO 没有有效优势信号。

## 18. LoRA-SFT 配置

```text
模型：                   Qwen2.5-1.5B-Instruct
框架：                   Transformers + TRL SFTTrainer + PEFT
精度：                   BF16
LoRA rank：              16
LoRA alpha：             32
target_modules：         q_proj、k_proj、v_proj、o_proj
per_device_batch_size：  1～2
gradient_accumulation：  4～8
max_seq_length：         768～1024
learning_rate：          1e-4～2e-4
epochs：                 2～3
gradient_checkpointing： 开启
use_cache：              关闭
```

SFT 验收标准：

```text
简单单设备任务合法工具调用率明显高于 Base
finish 不再大量提前出现
工具参数格式可被 HomeEnv 解析
验证集成功率高于随机工具调用基线
```

## 19. 在线 rollout 结构

同一个任务必须产生一组独立轨迹：

```text
scenario_i
   |
   +--> env_i_1.reset(same scenario) -> policy sample_1 -> R_i_1
   +--> env_i_2.reset(same scenario) -> policy sample_2 -> R_i_2
   +--> env_i_3.reset(same scenario) -> policy sample_3 -> R_i_3
```

每条轨迹保存：

```text
prompt_ids
completion_ids
completion_mask
old_per_token_logps
tool_calls
tool_results
episode_reward
reward_components
terminated / truncated
```

TRL 第一版优先使用自定义 `rollout_func`，因为 HomeFlow 需要同时保存多轮上下文、工具执行结果和 completion token 对齐信息。如果当前 TRL 版本的 `environment_factory` 已完整返回这些字段，再切换到环境工厂实现。HomeEnv 核心不因训练框架改变。

## 20. LoRA-GRPO 配置

```text
训练器：                 TRL GRPOTrainer
模型：                   SFT LoRA checkpoint
更新对象：               LoRA adapter
per_device_batch：       1
num_generations：        2 起步，稳定后改 4
max_prompt_length：      256～512
max_completion_length：  128～256
gradient_accumulation：  4～8
beta：                   0.02～0.1，单独记录
learning_rate：          1e-5～5e-5
gradient_checkpointing： 开启
use_cache：              关闭
reward model：           不加载
rollout：                Transformers 原生生成
vLLM：                   第一版关闭
```

本机先从 group=2 开始：

```text
同一 group 的 reward 全部相同
  -> 记录 degenerate_group_count
  -> 检查任务难度、工具格式和 reward 分解
  -> 不直接提高学习率
```

## 21. Reward 传递和防止投机

```text
HomeEnv state transition
      |
      v
progress + valid/invalid action + final predicate
      |
      v
episode reward
      |
      v
GRPO group normalization
```

DeepSeek 不参与在线 reward，也不参与最终测评打分。它只负责训练前的成功轨迹和语言表达变体。

第一版必须限制：

```text
只调用 finish，不执行动作
重复同一动作刷 completion
不断 query 拖延结束
生成大量自然语言但不调用工具
构造不存在的 device_id
使用超范围参数
控制成功后再次覆盖成错误状态
```

对应规则：

```text
finish 前至少执行一次有效动作
无状态变化的动作不增加 completion
query 不提供正向完成奖励
每一步有轻微成本
非法动作不能改变状态
最终以 goal predicates 为唯一成功标准
```

## 22. 单卡显存配置

```text
模型：                   Qwen2.5-1.5B-Instruct
训练：                   BF16 LoRA
gradient_checkpointing： 开启
use_cache：              关闭
batch_size：             1
num_generations：        2 起步
prompt：                 256～512 tokens
completion：             128～256 tokens
reward model：           不加载
rollout：                Transformers 原生生成
vLLM：                   第一版关闭
```

OOM 降级顺序：

```text
先减 completion 长度
  -> 再减 num_generations
  -> 再减 prompt 长度
  -> 再减 micro-batch
  -> 最后评估 QLoRA
```

第一版不同时打开 QLoRA、vLLM、offload 和异步 rollout。否则无法判断显存瓶颈来自参数、激活、KV cache 还是框架进程。

# 第四部分 独立测评、验收和实施顺序

## 23. 测评流程

```text
读取冻结 eval scenario
  -> 初始化独立 HomeEnv
  -> 给模型用户请求和工具 schema
  -> 模型生成工具调用
  -> 执行并返回 tool result
  -> 直到成功、失败或截断
  -> 读取 HomeEnv final_result
  -> 写入 metrics.jsonl
```

测评不读取 DeepSeek 轨迹，不使用文本相似度作为主要指标。

## 24. 必须记录的指标

```text
task_success_rate：     任务成功率
valid_action_rate：     合法工具调用率
illegal_action_rate：   非法工具调用率
finish_success_rate：   正确 finish 比例
avg_turns：             平均 assistant turn 数
avg_tool_calls：        平均工具调用数
avg_completion_tokens： 平均生成 token 数
avg_episode_reward：    平均环境 reward
degenerate_group_rate： RL 中 reward 无方差的 group 比例
clarification_rate：    澄清任务的正确处理比例
```

至少比较：

```text
Base vs SFT：    教师轨迹是否提高工具调用能力
SFT vs RL：      HomeEnv GRPO 是否进一步提高成功率
SFT vs Oracle：  当前模型距离规则上限还有多远
```

## 25. 测评子集

```text
seen_template：       训练见过模板，测试新 seed
unseen_combination：  训练见过设备，但没见过目标组合
unseen_paraphrase：   训练没见过用户表达方式
hard_negative：       非法参数、重复动作和提前 finish 诱因
```

如果只在 `seen_template` 提升，说明模型主要记忆了任务格式；`unseen_combination` 和 `unseen_paraphrase` 也提升，才说明策略有一定泛化。

## 26. Demo 推荐规模

第一轮只验证闭环：

```text
训练场景：             80
验证场景：             20
测评场景：             40
每个训练场景成功轨迹： 1～2 条
SFT 样本：             120～180 条
RL prompts：           40～80 条
GRPO group：           2
训练步数：             30～80 steps
```

第二轮再扩大到可报告规模：

```text
训练场景：             240
验证场景：             60
测评场景：             100
每个训练场景成功轨迹： 1～3 条
SFT 样本：             500～700 条
RL prompts：           150～240 条
GRPO group：           4
训练步数：             100～300 steps
```

第二轮适合做：

```text
Base / SFT / RL 对照
LoRA rank 8 / 16 / 32 对照
reward shaping 开关对照
DeepSeek 轨迹 / 程序规划轨迹对照
```

## 27. 阶段验收

```text
验收 1：状态机
  同一 seed + 同一 turn 序列，最终状态和 reward 完全一致。

验收 2：非法动作
  非法动作不会修改设备状态，error_code 稳定。

验收 3：规划轨迹
  每个 feasible 场景至少有一条成功轨迹。

验收 4：DeepSeek 数据
  API 原始响应、解析结果、HomeEnv 结果可以追溯。

验收 5：SFT
  模型能稳定生成合法 tool_call，并完成简单任务。

验收 6：RL rollout
  同一场景的 group 轨迹互不污染，reward 存在可见方差。

验收 7：GRPO
  adapter 能保存、恢复，训练后评测可重复。

验收 8：独立测评
  Base、SFT、RL 使用同一 eval 场景和同一指标脚本。
```

## 28. API 与数据安全

```text
DEEPSEEK_API_KEY 只从环境变量读取
原始 API 响应保存到 data_raw，不直接覆盖处理后数据
每次请求保存 request_id、model、prompt_version 和 timestamp
解析失败保留 error，不静默丢弃
训练数据不保存 API key
测评集不发送给 DeepSeek 生成标准答案后再回收使用
```

测评集必须在教师调用前完成冻结。如果需要让 DeepSeek 帮忙改写测评用户请求，应只发送结构化任务描述，不让它生成或返回可直接作为标准答案的轨迹，避免教师轨迹泄漏。

## 29. 实验记录

每次实验保存：

```text
git_commit
config.yaml
model_id
adapter_id
scenario_split_hash
prompt_version
reward_version
random_seed
GPU 显存峰值
训练时间
checkpoint 路径
eval metrics
```

HomeEnv 或 reward 改版后，旧 RL 结果不能直接与新版结果混比。

## 30. 最终实施顺序

```text
第 1 步：实现 homeflow_demo/env
  先写状态、工具校验、谓词和原子动作 reward。

第 2 步：写程序规划器
  不依赖 DeepSeek，确保 feasible 场景有标准成功轨迹。

第 3 步：完成 V1.1 turn-level 契约
  增加 AssistantTurn、ToolEvent、TurnResult，统一 max_turns，补齐回归测试。

第 4 步：接 DeepSeek API
  生成候选轨迹，原始响应和验证结果分开存储。

第 5 步：构造 SFT 数据并训练 Qwen LoRA
  先让模型学会工具格式和基本策略。

第 6 步：接 TRL rollout_func 或 environment_factory
  在线采样 HomeEnv 轨迹，检查 reward 方差和轨迹独立性。

第 7 步：运行 LoRA-GRPO
  从 group=2、短序列开始，再逐步增加到 group=4。

第 8 步：运行 Base/SFT/RL 独立评测
  只由 HomeEnv 判定任务成功，不用 DeepSeek 评测模型。
```

## 31. Demo 完成标准

```text
HomeEnv 能稳定判断成功和失败
DeepSeek 能批量生成可追溯候选轨迹
程序规划器能保证可行场景有成功样本
SFT 能让模型学会合法工具调用
LoRA-GRPO 能在任务组内获得非零优势信号
RL checkpoint 在冻结 eval 集上可重复测评
```

完成这个 Demo 后，再考虑增加更多设备、时间推进、真实 Home Assistant/MCP、vLLM/SGLang、QLoRA、Hybrid-LoRA、MCTS 和 OpenRLHF/veRL 异步 rollout。
