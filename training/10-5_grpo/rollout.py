"""四路独立环境共享一个批量HF生成线程，记录真实采样token与完整前缀。"""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from new_demo.agents.A_policy import DeepSeekPolicy
from new_demo.agents.DeepSeek_client import DeepSeekResponse
from new_demo.eval.C_episode_runner import EpisodeRunner


class ContextBudgetExhausted(ValueError):
    """固定上下文预算耗尽，单独记为agent预算终止。"""


class HFBackend:
    """原生HF批量采样后端，模型只在一个线程内生成。"""

    def __init__(self, model, tokenizer, config):
        """接收共享policy模型及固定采样配置，不另载推理模型。"""
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.batches = []

    def generate(self, requests):
        """左padding同批请求，截取真正生成的token并保留实际EOS。"""
        import torch
        started = time.perf_counter()
        encoded = self.tokenizer.pad({"input_ids": [item["input_ids"] for item in requests]}, padding=True, return_tensors="pt")
        encoded = {key: value.to("cuda") for key, value in encoded.items()}
        prompt_width = encoded["input_ids"].shape[1]
        cap = min(self.config["max_new_tokens"], self.config["max_length"] - prompt_width)
        if cap < 1:
            raise ContextBudgetExhausted("no room for a sampled action")
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            output = self.model.generate(**encoded, do_sample=True, temperature=self.config["temperature"], top_p=1.0, top_k=0, repetition_penalty=1.0, max_new_tokens=cap, use_cache=True, eos_token_id=self.tokenizer.eos_token_id, pad_token_id=self.tokenizer.pad_token_id)
        results = []
        for item in output[:, prompt_width:].tolist():
            if self.tokenizer.eos_token_id in item:
                item = item[:item.index(self.tokenizer.eos_token_id) + 1]
            results.append({"generated_ids": item, "content": self.tokenizer.decode(item, skip_special_tokens=True), "generation_cap": cap})
        self.batches.append({"size": len(requests), "prompt_lengths": [len(item["input_ids"]) for item in requests], "completion_lengths": [len(item["generated_ids"]) for item in results], "seconds": round(time.perf_counter() - started, 3)})
        return results


class BatchService:
    """收集四个episode的请求，等待短窗口后动态组成一个生成批次。"""

    def __init__(self, backend, parallel):
        """创建唯一生成线程与请求队列；结束必须显式close。"""
        self.backend = backend
        self.parallel = parallel
        self.requests = queue.Queue()
        self.thread = threading.Thread(target=self._serve, name="grpo-hf-batcher")
        self.thread.start()

    def submit(self, request):
        """每个请求关联独立Future，避免把不同家庭的回执串到一起。"""
        future = Future()
        self.requests.put((request, future))
        return future

    def _serve(self):
        """单线程执行生成；基础设施异常传给所有对应请求，不计普通错误罚分。"""
        while True:
            first = self.requests.get()
            if first is None:
                return
            batch = [first]
            deadline = time.monotonic() + 0.08
            while len(batch) < self.parallel:
                try:
                    item = self.requests.get(timeout=max(0.001, deadline - time.monotonic()))
                    if item is None:
                        raise RuntimeError("batch service closed with outstanding requests")
                    batch.append(item)
                except queue.Empty:
                    break
            try:
                values = self.backend.generate([item[0] for item in batch])
                if len(values) != len(batch):
                    raise ValueError("backend result count differs from requests")
                for (_, future), value in zip(batch, values):
                    future.set_result(value)
            except Exception as exc:
                for _, future in batch:
                    future.set_exception(exc)

    def close(self):
        """episode都结束后关闭生成线程，禁止遗留后台GPU工作。"""
        self.requests.put(None)
        self.thread.join()


class ActorClient:
    """把批量生成包装成现有A_policy客户端，私有保存每条轨迹的采样调用。"""

    def __init__(self, service, tokenizer, config):
        """一个episode一个客户端，会话和token记录不会跨轨迹共用。"""
        self.service = service
        self.tokenizer = tokenizer
        self.config = config
        self.calls = []
        self.infrastructure_errors = []
        self.budget_exhausted = False

    def complete(self, messages, *, role, request_id=None, temperature=None):
        """严格记录本次前缀和生成token；未生成的错误文本不变成策略目标。"""
        if role != "A":
            raise ValueError("actor only accepts A")
        input_ids = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        if len(input_ids) >= self.config["max_length"]:
            self.budget_exhausted = True
            raise ContextBudgetExhausted("episode context budget exhausted")
        started = time.perf_counter()
        try:
            result = self.service.submit({"input_ids": input_ids}).result()
        except ContextBudgetExhausted:
            self.budget_exhausted = True
            raise
        except Exception as exc:
            self.infrastructure_errors.append(type(exc).__name__)
            raise
        self.calls.append({"input_ids": input_ids, "generated_ids": result["generated_ids"], "content": result["content"], "generation_cap": result["generation_cap"]})
        return DeepSeekResponse(request_id=request_id or "local", role=role, content=result["content"], raw_response={}, usage={"prompt_tokens": len(input_ids), "completion_tokens": len(result["generated_ids"])}, elapsed_ms=(time.perf_counter() - started) * 1000, model="local-grpo-policy")


def run_episode(task, service, tokenizer, config, branch):
    """独立reset一个家庭，沿用A/C/B，另存group与分支标识。"""
    client = ActorClient(service, tokenizer, config)
    result = EpisodeRunner(DeepSeekPolicy(client)).run(task["scenario"])
    return {"sample_id": task["sample_id"], "group_id": "smoke-" + task["sample_id"], "rollout_id": f"{task['sample_id']}-branch-{branch}", "category": task["category"], "scenario": task["scenario"], "record": result.record, "labels": result.labels.to_dict(), "calls": client.calls, "context_budget_exhausted": client.budget_exhausted, "infrastructure_errors": client.infrastructure_errors}


def generate_group(task, service, tokenizer, config):
    """同任务四条独立随机路径同时请求生成，policy参数期间保持不变。"""
    with ThreadPoolExecutor(max_workers=config["rollout_parallel"]) as pool:
        futures = [pool.submit(run_episode, task, service, tokenizer, config, branch) for branch in range(config["num_generations"])]
        return [future.result() for future in futures]


def pack_calls(calls, max_length):
    """逐token核对实际前缀再打包，观察可见但仅真实生成token参与策略loss。"""
    if not calls:
        raise ValueError("empty sampled trajectory")
    packed = calls[-1]["input_ids"] + calls[-1]["generated_ids"]
    if len(packed) > max_length:
        raise ValueError("packed sampled trajectory exceeds context budget")
    mask = [0] * len(packed)
    previous_end = 0
    for call in calls:
        start = len(call["input_ids"])
        end = start + len(call["generated_ids"])
        if start < previous_end or packed[:start] != call["input_ids"] or packed[start:end] != call["generated_ids"]:
            raise ValueError("sampled prefix cannot be reproduced by packed tokens")
        mask[start:end] = [1] * (end - start)
        previous_end = end
    return {"input_ids": packed, "policy_mask": mask, "sampled_tokens": sum(mask)}
