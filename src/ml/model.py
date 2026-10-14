"""1D Convolutional Autoencoder for repository activity anomaly detection.

Architecture
------------
Input : (batch, 2, 28)  — 2 channels (log-commits, log-churn), 28-day window

Encoder
  Conv1d(2→16, k=5, pad=2)  → ReLU
  MaxPool1d(2)               → (batch, 16, 14)
  Conv1d(16→32, k=5, pad=2) → ReLU
  MaxPool1d(2)               → (batch, 32, 7)
  Flatten                    → (batch, 224)
  Linear(224→16)             → latent code

Decoder
  Linear(16→224)
  Reshape → (batch, 32, 7)
  Upsample(×2)               → (batch, 32, 14)
  Conv1d(32→16, k=5, pad=2) → ReLU
  Upsample(×2)               → (batch, 16, 28)
  Conv1d(16→2, k=5, pad=2)  → reconstruction

Loss : MSE
"""

from __future__ import annotations

try:
    import torch
    import torch.nn as nn
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


WINDOW_SIZE = 28    # days per sliding window
LATENT_DIM  = 16


def is_torch_available() -> bool:
    return _TORCH_AVAILABLE


if _TORCH_AVAILABLE:
    class ActivityAutoencoder(nn.Module):
        """1D convolutional autoencoder for 28-day activity windows."""

        def __init__(self) -> None:
            super().__init__()

            # Encoder
            self.encoder = nn.Sequential(
                nn.Conv1d(2, 16, kernel_size=5, padding=2),  # (B, 16, 28)
                nn.ReLU(),
                nn.MaxPool1d(2),                              # (B, 16, 14)
                nn.Conv1d(16, 32, kernel_size=5, padding=2), # (B, 32, 14)
                nn.ReLU(),
                nn.MaxPool1d(2),                              # (B, 32, 7)
            )
            self.enc_fc = nn.Linear(32 * 7, LATENT_DIM)

            # Decoder
            self.dec_fc = nn.Linear(LATENT_DIM, 32 * 7)
            self.decoder = nn.Sequential(
                nn.Upsample(scale_factor=2),                  # (B, 32, 14)
                nn.Conv1d(32, 16, kernel_size=5, padding=2), # (B, 16, 14)
                nn.ReLU(),
                nn.Upsample(scale_factor=2),                  # (B, 16, 28)
                nn.Conv1d(16, 2, kernel_size=5, padding=2),  # (B, 2, 28)
            )

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            # Encode
            h = self.encoder(x)            # (B, 32, 7)
            h = h.view(h.size(0), -1)      # (B, 224)
            z = self.enc_fc(h)             # (B, 16) — latent code

            # Decode
            h = self.dec_fc(z)             # (B, 224)
            h = h.view(h.size(0), 32, 7)  # (B, 32, 7)
            out = self.decoder(h)          # (B, 2, 28)
            return out

        def encode(self, x: "torch.Tensor") -> "torch.Tensor":
            h = self.encoder(x)
            h = h.view(h.size(0), -1)
            return self.enc_fc(h)

else:
    # Stub so the rest of the codebase can import without crashing
    class ActivityAutoencoder:  # type: ignore[no-redef]
        def __init__(self) -> None:
            raise ImportError("PyTorch is not installed. Install it with: pip install torch")
