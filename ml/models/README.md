# PisGO Model Artifacts

Model weights and serialized classifiers are intentionally excluded from the Git repository.

## Public Release Downloads

Pretrained model checkpoints are available from GitHub Releases:
* **Release**: [`aic-preliminary-models-v1`](https://github.com/Vluuuu/pisgo/releases/tag/aic-preliminary-models-v1)
* **Release Title**: `PisGo AIC Preliminary Model Artifacts v1`

### 1. YOLOv11n Banana Bunch Presence Gate
* **File**: `banana_bunch_yolo11n_emergency_v1.pt`
* **Size**: `21,234,723 bytes`
* **Format**: PyTorch checkpoint (Ultralytics YOLOv11n)
* **SHA-256**: `d8e3ca2b0305a0755cae707f2969486674d98761d14b2c79a02a43ba7f5ce26e`
* **Direct URL**: `https://github.com/Vluuuu/pisgo/releases/download/aic-preliminary-models-v1/banana_bunch_yolo11n_emergency_v1.pt`

### 2. Cavendish Visual Maturity Classifier
* **File**: `cavendish_maturity_classifier.joblib`
* **Size**: `15,409 bytes`
* **Format**: Compressed Joblib/Pickle dictionary
* **SHA-256**: `117c1f134670ac9b3ebc1b9d3f8a1d81549ec3fbd23f159b741238325f187c9e`
* **Direct URL**: `https://github.com/Vluuuu/pisgo/releases/download/aic-preliminary-models-v1/cavendish_maturity_classifier.joblib`

## Download & Placement

To place artifacts in `ml/models/`:

```bash
# Using GitHub CLI
gh release download aic-preliminary-models-v1 --dir ml/models

# Or using curl
curl -L -o ml/models/banana_bunch_yolo11n_emergency_v1.pt \
  https://github.com/Vluuuu/pisgo/releases/download/aic-preliminary-models-v1/banana_bunch_yolo11n_emergency_v1.pt

curl -L -o ml/models/cavendish_maturity_classifier.joblib \
  https://github.com/Vluuuu/pisgo/releases/download/aic-preliminary-models-v1/cavendish_maturity_classifier.joblib
```
