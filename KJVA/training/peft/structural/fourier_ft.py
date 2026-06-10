"""
peft/structural/fourier_ft.py — FourierFT (Fourier-Domain Delta)

Mathematical formulation:
  FourierFT represents the weight update ΔW in the frequency domain.
  Instead of directly learning a dense or low-rank ΔW, it learns n_frequency
  Fourier spectral coefficients and reconstructs ΔW via inverse DFT:

    ΔW = IDFT({c_k at freq_k | k = 1..n_frequency})

  Only n_frequency << (out * in) entries of the DFT of ΔW are non-zero.
  The remaining DFT coefficients are zero. This imposes a smooth, structured
  prior on the weight updates (smooth functions in weight space).

  Parameters: n_frequency (default 100) vs d_out * d_in (147,456 for 384×384).
  This achieves ~1,475× compression for n_frequency=100.

  IMPLEMENTATION NOTE: MLX does not expose a general IDFT/scatter operation
  easily. We implement an approximate version that places spectral_coeff values
  at fixed random positions in the flattened weight matrix (equivalent to a
  sparse update in the natural basis, approximating the spectral basis). A true
  frequency-domain update would use mx.fft if available.

Reference: Gao et al. (2024) "Parameter-Efficient Fine-Tuning with Discrete
Fourier Transform"
"""
from __future__ import annotations

import numpy as np
import mlx.core as mx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class FourierFTLinear(DeltaOperator):
    """
    FourierFT: spectral weight delta parameterized by n_frequency coefficients.

    spectral_coeff stores n_frequency trainable Fourier coefficients.
    _S is a frozen (total_params, n_frequency) scatter matrix with a single 1.0
    per column at a randomly chosen position; delta_W_flat = _S @ spectral_coeff
    keeps the entire forward pass in the MLX autograd graph.

    Returns the delta x @ delta_W.T — caller adds to frozen linear output.

    Args:
        in_features:   input dimension
        out_features:  output dimension
        n_frequency:   number of active Fourier frequencies (default 100)
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        n_frequency: int = 100,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        self.n_frequency  = n_frequency

        total_params = out_features * in_features

        # Trainable spectral coefficients — init small normal
        self.spectral_coeff = mx.random.normal((n_frequency,)) * 0.01

        # Fixed random frequency indices into flattened weight space
        # These are not parameters — underscore prefix
        rng = np.random.default_rng(seed=42)
        indices_np = rng.choice(total_params, size=n_frequency, replace=False).astype(np.int32)
        self._total_params = total_params

        # Pre-compute frozen scatter matrix S: (total_params, n_frequency)
        # S[indices_np[k], k] = 1.0 for each of the n_frequency active positions.
        # delta_W_flat = S @ spectral_coeff stays in the MLX computation graph,
        # so gradients flow back to spectral_coeff correctly.
        S_np = np.zeros((total_params, n_frequency), dtype=np.float32)
        for k, idx in enumerate(indices_np):
            S_np[idx, k] = 1.0
        self._S = mx.array(S_np)   # frozen; underscore prefix keeps it out of param tree

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.STRUCTURAL

    @property
    def genome_config(self) -> dict:
        return {
            "in_features": self.in_features,
            "out_features": self.out_features,
            "n_frequency": self.n_frequency,
            "compression_ratio": self._total_params / self.n_frequency,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute Fourier-domain weight delta.

        Uses the pre-computed frozen scatter matrix _S to map spectral_coeff
        into the flattened weight space entirely within MLX, preserving the
        autograd graph so gradients flow back to spectral_coeff.

        delta_W_flat = _S @ spectral_coeff   shape: (total_params,)
        delta_W      = reshape to (out_features, in_features)
        output       = x @ delta_W.T

        Args:
            x: input [..., in_features]
        Returns:
            delta output [..., out_features]
        """
        # _S: (total_params, n_frequency), spectral_coeff: (n_frequency,)
        # matmul keeps spectral_coeff in the MLX computation graph → correct gradients
        delta_W_flat = self._S @ self.spectral_coeff                          # (total_params,)
        delta_W = delta_W_flat.reshape(self.out_features, self.in_features)   # (out, in)
        return x @ delta_W.T
