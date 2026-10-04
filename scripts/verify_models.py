#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_models.py — 模型下载完成后的完整性校验与清单登记

输入
  /root/autodl-tmp/models/ 下六个目录（download_models.sh 的产物）
    <模型名>/hf/     HF 整仓库（safetensors + tokenizer + config）
    <模型名>/gguf/   GGUF Q8_0 单文件

输出
  1) 控制台校验报告（人看的）
  2) scripts/model_manifest.json  机器可读清单，供后续训练/评测脚本引用
  3) scripts/model_manifest.md    人类可读清单（与 json 同步生成）

校验口径
  GGUF：算 SHA-256，对 source.md §3 登记的 Windows 端同名文件哈希；
        对得上说明与旧评测（newdoc/05、12）同源同量化
  HF  ：没有外部哈希可对，检查关键文件齐全（safetensors / config / tokenizer）
        并登记文件清单与总大小
退出码：0 = 全部通过；1 = 有缺文件或哈希不符
"""

import hashlib
import json
import sys
from pathlib import Path

MODELS = Path("/root/autodl-tmp/models")          # 权重根目录
OUT_DIR = Path(__file__).resolve().parent          # 本脚本所在目录（scripts/）

# 三个 GGUF 目标：期望哈希来自 source.md §3 的 Windows 端登记值
GGUF_TARGETS = [
    dict(name="Qwen3-0.6B", sub="Qwen3-0.6B/gguf", file="Qwen3-0.6B-Q8_0.gguf",
         source="Qwen/Qwen3-0.6B-GGUF", quant="Q8_0",
         sha256="9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031"),
    dict(name="Qwen2.5-1.5B-Instruct", sub="Qwen2.5-1.5B-Instruct/gguf",
         file="qwen2.5-1.5b-instruct-q8_0.gguf",
         source="Qwen/Qwen2.5-1.5B-Instruct-GGUF", quant="Q8_0",
         sha256="d7efb072e7724d25048a4fda0a3e10b04bdef5d06b1403a1c93bd9f1240a63c8"),
    dict(name="Qwen3.5-2B", sub="Qwen3.5-2B/gguf", file="Qwen3.5-2B-Q8_0.gguf",
         source="unsloth/Qwen3.5-2B-GGUF", quant="Q8_0",
         sha256="1b04acba824817554f4ce23639bc8495ff70453b8fcb047900c731521021f2c1"),
]

# 三个 HF 训练仓库：must_have 是训练加载必需文件
HF_TARGETS = [
    dict(name="Qwen3-0.6B", sub="Qwen3-0.6B/hf", source="Qwen/Qwen3-0.6B",
         must_have=["config.json", "model.safetensors"]),
    dict(name="Qwen2.5-1.5B-Instruct", sub="Qwen2.5-1.5B-Instruct/hf",
         source="Qwen/Qwen2.5-1.5B-Instruct",
         must_have=["config.json", "model.safetensors"]),
    dict(name="Qwen3.5-2B", sub="Qwen3.5-2B/hf", source="Qwen/Qwen3.5-2B",
         must_have=["config.json", "model.safetensors-00001-of-00001.safetensors"]),
]


def sha256_of(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    """分块计算文件 SHA-256，8MB 一块，避免大文件一次性读进内存。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def check_gguf(t: dict) -> dict:
    """校验一个 GGUF 目标：存在性 + 大小 + SHA-256 是否对上登记值。"""
    path = MODELS / t["sub"] / t["file"]
    rec = dict(kind="gguf", name=t["name"], source=t["source"], quant=t["quant"],
               path=str(path), ok=False)
    if not path.exists():
        rec["error"] = "文件不存在"
        return rec
    rec["size_bytes"] = path.stat().st_size
    rec["sha256"] = sha256_of(path)
    rec["sha256_expected"] = t["sha256"]
    rec["ok"] = rec["sha256"] == t["sha256"]
    return rec


def check_hf(t: dict) -> dict:
    """校验一个 HF 仓库：关键文件齐全 + 登记完整文件清单和总大小。"""
    root = MODELS / t["sub"]
    rec = dict(kind="hf", name=t["name"], source=t["source"],
               path=str(root), ok=False, files=[])
    if not root.is_dir():
        rec["error"] = "目录不存在"
        return rec
    total = 0
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rec["files"].append(dict(name=str(p.relative_to(root)), size_bytes=p.stat().st_size))
            total += p.stat().st_size
    rec["size_bytes"] = total
    rec["missing"] = [m for m in t["must_have"] if not (root / m).exists()]
    rec["ok"] = not rec["missing"]
    return rec


def fmt_md(manifest: dict) -> str:
    """把清单渲染成人类可读的中文 Markdown。"""
    lines = ["# model_manifest — 服务器模型权重登记", "",
             f"> 生成时间：{manifest['generated_at']}　生成脚本：`scripts/verify_models.py`",
             f"> 校验结果：{'全部通过 ✅' if manifest['all_ok'] else '有失败项 ❌'}", "",
             "## 1 总览", "",
             "| 模型 | 格式 | 来源 (ModelScope) | 大小 | 校验 |", "|---|---|---|---|---|"]
    for r in manifest["records"]:
        size = f"{r['size_bytes']/1e9:.2f} GB" if "size_bytes" in r else "-"
        mark = "✅" if r["ok"] else "❌ " + r.get("error", "哈希不符")
        lines.append(f"| {r['name']} | {r['kind']} | {r['source']} | {size} | {mark} |")
    lines += ["", "## 2 GGUF 哈希对账（对 source.md §3 的 Windows 端登记值）", "",
              "| 文件 | SHA-256 | 对上登记值 |", "|---|---|---|"]
    for r in manifest["records"]:
        if r["kind"] == "gguf" and "sha256" in r:
            lines.append(f"| {r['path'].split('/')[-1]} | `{r['sha256']}` | {'是' if r['ok'] else '**否**'} |")
    lines += ["", "## 3 HF 仓库文件清单", ""]
    for r in manifest["records"]:
        if r["kind"] == "hf":
            lines.append(f"### {r['name']}（{r['source']}，{r.get('size_bytes',0)/1e9:.2f} GB）")
            lines.append("")
            lines.append("```text")
            for f in r.get("files", []):
                lines.append(f"{f['size_bytes']/1e6:10.1f} MB  {f['name']}")
            lines.append("```")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    """跑全部校验，打印报告，写 manifest.json 与 manifest.md。"""
    import datetime
    records = [check_gguf(t) for t in GGUF_TARGETS] + [check_hf(t) for t in HF_TARGETS]
    all_ok = all(r["ok"] for r in records)
    manifest = dict(generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    host="autodl-18378", root=str(MODELS),
                    all_ok=all_ok, records=records)

    # 控制台报告
    print(f"{'模型':<24}{'格式':<6}{'大小':>10}  校验")
    for r in records:
        size = f"{r['size_bytes']/1e9:.2f} GB" if "size_bytes" in r else "-"
        print(f"{r['name']:<24}{r['kind']:<6}{size:>10}  "
              f"{'OK' if r['ok'] else 'FAIL: ' + str(r.get('error') or '哈希不符')}")

    # 落盘 json + md
    (OUT_DIR / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "model_manifest.md").write_text(fmt_md(manifest), encoding="utf-8")
    print(f"\nmanifest 已写：{OUT_DIR/'model_manifest.json'} / model_manifest.md")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
