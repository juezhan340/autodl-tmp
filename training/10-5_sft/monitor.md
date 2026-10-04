# monitor.py 中文说明

```text
职责：独立只读HTTP服务，将真实运行状态投影到浏览器。
输入：配置路径、监听host和port，默认0.0.0.0:6008。
输出：GET /、/dashboard.html、/api/status、/healthz。
读取：sft-main中的状态、指标、checkpoint索引；数据manifest；nvidia-smi。
写入：无训练数据写入，仅标准输出启动信息。
不负责：加载模型、占用CUDA、启动/停止训练、提供任意文件下载。
对应文件：monitor.py、dashboard.html；后台启动入口launch.py。
```

浏览器每3秒轮询；GPU查询缓存5秒。正式运行尚未开始时返回not_started，已有旧smoke不会显示成正式进度。训练PID与启动标识不匹配时，返回interrupted，不修改训练进程留下的文件。读取正在追加的metrics时仅忽略未写完的末行；完整坏行返回503。

接口只公开模型名、配置、数据计数、指标和checkpoint名称/校验值，不公开环境变量、密钥、仓库目录或任意文件。HEAD使用同一路由、仅返回响应头，支持平台健康探测；POST返回405，非白名单路径404。公网映射没有身份认证，因此只提供这类只读信息；需要私有指标时应在平台侧限制访问。

```text
监听：0.0.0.0:6008
本机：http://127.0.0.1:6008
公网：https://uu753393-afb3-4b7a916d.westd.seetacloud.com:8443
```

公网地址采用用户提供的实例映射。服务可以确认本机响应，公网可达性还取决于平台转发。
