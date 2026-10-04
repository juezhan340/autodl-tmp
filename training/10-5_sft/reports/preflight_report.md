# preflight_report.json 中文说明

本文件记录运行配置、统计或检查点元数据，不含密钥。

```json
{
  "full_training_started": false,
  "test_set_model_evaluated": false,
  "external_judge_called": false,
  "data_counts": {
    "train": 500,
    "validation": 100,
    "test": 200,
    "reserve": 194
  },
  "max_tokens": {
    "train": 2689,
    "validation": 2696,
    "test": 2695,
    "reserve": 2632
  },
  "target_tokens": {
    "train": 73875,
    "validation": 15015,
    "test": 30086,
    "reserve": 29022
  },
  "data_manifest_sha256": "fd11810928323eb2854ae4408f96292fdab831a00d0fdcb331f5e27a23fbcff8",
  "teacher_replay": [
    {
      "sample_id": "sc_T1_104",
      "category": "T1",
      "labels": {
        "C-1": true,
        "C-2": true,
        "C-3": true,
        "C-4": true
      }
    },
    {
      "sample_id": "sc_T2_259",
      "category": "T2",
      "labels": {
        "C-1": true,
        "C-2": true,
        "C-3": true,
        "C-4": true
      }
    },
    {
      "sample_id": "sc_T3_019",
      "category": "T3",
      "labels": {
        "C-1": true,
        "C-2": true,
        "C-3": true,
        "C-4": true
      }
    },
    {
      "sample_id": "sc_T4_146",
      "category": "T4",
      "labels": {
        "C-1": true,
        "C-2": true,
        "C-3": true,
        "C-4": true
      }
    },
    {
      "sample_id": "sc_T5_067",
      "category": "T5",
      "labels": {
        "C-1": true,
        "C-2": true,
        "C-3": true,
        "C-4": true
      }
    }
  ],
  "versions": {
    "torch": "2.8.0+cu128",
    "transformers": "4.57.3",
    "trl": "0.24.0",
    "peft": "0.18.0",
    "accelerate": "1.11.0",
    "datasets": "4.4.1",
    "tokenizers": "0.22.1",
    "safetensors": "0.7.0"
  },
  "gpu_smoke": {
    "mode": "smoke",
    "full_training_started": false,
    "train_count": 500,
    "validation_count": 100,
    "test_count": 200,
    "effective_batch": 8,
    "run_dir": "/root/autodl-tmp/training_runs/10-5_sft/smoke-20261004T163324792671Z",
    "updates": 2,
    "training_examples_used": 2,
    "epochs_completed": 2.0,
    "checkpoint_count": 2,
    "best_checkpoint": "/root/autodl-tmp/training_runs/10-5_sft/smoke-20261004T163324792671Z/checkpoint-2",
    "selected_adapter": "/root/autodl-tmp/training_runs/10-5_sft/smoke-20261004T163324792671Z/selected_adapter",
    "training_loss": 0.30864541232585907,
    "elapsed_seconds": 4.767,
    "gpu_peak_allocated_mib": 13041.9,
    "gpu_peak_reserved_mib": 18868.0,
    "trainable_parameters": 18464768,
    "verified_adapter_paths": [
      "/root/autodl-tmp/training_runs/10-5_sft/smoke-20261004T163324792671Z/checkpoint-1",
      "/root/autodl-tmp/training_runs/10-5_sft/smoke-20261004T163324792671Z/checkpoint-2",
      "/root/autodl-tmp/training_runs/10-5_sft/smoke-20261004T163324792671Z/selected_adapter"
    ],
    "base_weights_unchanged": true,
    "environment_interface_test": {
      "split": "train",
      "model": "/root/autodl-tmp/models/Qwen2.5-1.5B-Instruct/hf",
      "adapter": "/root/autodl-tmp/training_runs/10-5_sft/smoke-20261004T163324792671Z/selected_adapter",
      "few_shot": false,
      "semantic_judge": "off",
      "total": 5,
      "per_category": {
        "T1": {
          "total": 1,
          "program_success": 0,
          "final_success": 0,
          "pending_semantic": 0,
          "c_failures": {
            "C-2": 1,
            "C-4": 1
          }
        },
        "T2": {
          "total": 1,
          "program_success": 0,
          "final_success": 0,
          "pending_semantic": 0,
          "c_failures": {
            "C-2": 1
          }
        },
        "T3": {
          "total": 1,
          "program_success": 0,
          "final_success": 0,
          "pending_semantic": 0,
          "c_failures": {
            "C-2": 1
          }
        },
        "T4": {
          "total": 1,
          "program_success": 0,
          "final_success": 0,
          "pending_semantic": 0,
          "c_failures": {
            "C-3": 1,
            "C-4": 1
          }
        },
        "T5": {
          "total": 1,
          "program_success": 0,
          "final_success": 0,
          "pending_semantic": 0,
          "c_failures": {
            "C-4": 1
          }
        }
      },
      "generation_attempts": 17,
      "successful_generations": 17,
      "generation_errors": 0,
      "scope": "environment_evaluation_not_teacher_forced_accuracy"
    }
  }
}
```
