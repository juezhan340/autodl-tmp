# D3_reviewer.py

职责：
  D3 两步。程序先扫硬泄露；过了再用 共用的 D3_review.md问外部 DeepSeek。

输入：
  category、task、user_request、intent。

输出：
  accept、codes、stage=program|model。不过则不发 blueprint_id。

读取：
  第一步只读 user_request 和 task 里的 id。
  第二步读 D3_review.md，不读 home。

写入：
  无。失败记录由编排写 D34_failures.jsonl。

不负责：
  打 B、当 A。

对应文件：
  new_demo/data/D3_reviewer.py
