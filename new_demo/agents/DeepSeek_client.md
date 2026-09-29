# DeepSeek_client.py

职责：
  共用客户端。role=A 与 role=external 都不写 max_tokens。

输入：
  messages、role、request_id。
  配置来自 new_demo/.env.deepseek。

输出：
  DeepSeekResponse；complete_json 再解析成对象。

读取：
  .env.deepseek

写入：
  data_raw/api/ 下不含密钥的 JSONL。

不负责：
  拼提示词、判 task 对错。

对应文件：
  new_demo/agents/DeepSeek_client.py
