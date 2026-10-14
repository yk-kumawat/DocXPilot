This directory contains trained model weights and configuration.

Files expected after running `python src/ml/train.py`:
  - activity_ae.pt   : PyTorch model state dict
  - config.json      : normalization params, threshold, training metadata
  - loss_curve.png   : training loss visualization

These files are NOT committed to git (see .gitignore).
Run the training script to regenerate them.
