"""
peft/low_rank/qlora.py — QLoRA (Quantized LoRA)

Mathematical formulation:
  QLoRA keeps base model weights in low precision (4-bit NF4 quantization)
  while LoRA adapters remain in full float16/bfloat16:

    y = dequantize(W_q) @ x + B @ A @ x * scaling

  This allows loading 16B-parameter models in ~8GB VRAM by quantizing W
  to 4 bits (4× compression), then fine-tuning only the small LoRA adapters
  in fp16 precision.

  MLX IMPLEMENTATION NOTE: MLX provides `nn.QuantizedLinear` and
  `mx.quantize()` for 4-bit weight quantization. However, the quantized
  representation is handled internally by the MLX runtime — you cannot
  directly construct NF4 tensors as in bitsandbytes. This implementation:
    1. Creates a standard `nn.Linear` as a placeholder for the quantized base
    2. Attaches LoRA adapters in float32 (MLX's default)
    3. Provides `quantize_model_to_4bit()` which uses `nn.QuantizedLinear`
       to convert base weights at deployment time.

Reference: Dettmers et al. (2023) "QLoRA: Efficient Finetuning of Quantized LLMs"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator, kaiming_uniform


class QLoRALinear(DeltaOperator):
    """
    QLoRA: LoRA adapters operating on a (conceptually) quantized base weight.

    In this MLX implementation, the base linear is left as nn.Linear.
    The quantize_model_to_4bit() helper converts it to nn.QuantizedLinear
    at deployment. The LoRA adapters (lora_A, lora_B) remain float32.

    __call__ returns only the LoRA DELTA. The caller handles:
        output = quantized_base(x) + qlora_adapter(x)

    Args:
        in_features:  input dimension
        out_features: output dimension
        rank:         LoRA rank
        alpha:        LoRA scaling
        bits:         quantization bit-width (4 or 8; informational only in MLX)
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        rank: int = 8,
        alpha: float = 16.0,
        bits: int = 4,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        self.rank    = rank
        self.alpha   = alpha
        self.bits    = bits
        self.scaling = alpha / rank

        # NOTE: In full QLoRA, this would be nn.QuantizedLinear with NF4 weights.
        # MLX's nn.QuantizedLinear exists but requires weights to be quantized
        # via mx.quantize() before loading. We store a standard Linear as
        # a placeholder; quantize_model_to_4bit() converts it in-place.
        self.base_linear = nn.Linear(in_features, out_features, bias=False)
        # Freeze base weights — only LoRA adapters are trained
        self.base_linear.freeze()

        # LoRA adapters in float32 (full precision despite quantized base)
        self.lora_A = kaiming_uniform((rank, in_features))
        self.lora_B = mx.zeros((out_features, rank))

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.WEIGHT_ADDITIVE

    @property
    def genome_config(self) -> dict:
        return {
            "rank": self.rank,
            "alpha": self.alpha,
            "bits": self.bits,
            "scaling": self.scaling,
            "in_features": self.in_features,
            "out_features": self.out_features,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute LoRA delta (base weight handled separately).

        For QLoRA, combine with the quantized base:
            full_out = self.base_linear(x) + self(x)

        x: [..., in_features]
        returns: [..., out_features] (LoRA delta only)
        """
        return x @ self.lora_A.T @ self.lora_B.T * self.scaling


def quantize_model_to_4bit(model) -> object:
    """
    Convert all nn.Linear layers in a TokenlessLM to nn.QuantizedLinear
    and attach QLoRA adapters to each.

    MLX NOTE: `nn.QuantizedLinear.from_linear(linear, bits=4)` is the
    correct MLX API for converting an existing Linear to quantized form.
    If `from_linear` is not available in the installed MLX version,
    this function falls back to keeping the original Linear frozen.

    Args:
        model: TokenlessLM instance

    Returns:
        (model, adapters_dict) where adapters_dict maps layer path to QLoRALinear
    """
    adapters: dict[str, QLoRALinear] = {}

    for i, block in enumerate(model.blocks):
        attn = block.attn
        for proj_name in ("q", "k", "v", "o"):
            linear = getattr(attn, proj_name)
            in_f  = linear.weight.shape[1]
            out_f = linear.weight.shape[0]

            # Attempt MLX quantization
            try:
                q_linear = nn.QuantizedLinear.from_linear(linear, bits=4)
                setattr(attn, proj_name, q_linear)
            except (AttributeError, NotImplementedError):
                # Fallback: freeze linear if quantization API not available
                linear.freeze()

            adapter = QLoRALinear(in_f, out_f, rank=8, bits=4)
            adapters[f"block_{i}.attn.{proj_name}"] = adapter

    return model, adapters
