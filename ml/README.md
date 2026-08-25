# PisGO Machine Learning

Machine Learning pipelines for the PisGO decision-support system.

## 1. Current MVP Runtime Models

PisGO uses a two-stage inference architecture: presence gating followed by visual maturity classification.

### Stage 1: Banana Bunch Presence Gate (YOLOv11n)
* **Model**: Ultralytics YOLOv11n fine-tuned for class-0 (`banana_bunch`) detection.
* **Role**: Presence gate only. If no banana bunch is detected at confidence threshold $\ge 0.25$, downstream maturity inference is bypassed and null-safe outputs are returned.
* **Artifact**: `models/banana_bunch_yolo11n_emergency_v1.pt` (SHA-256: `d8e3ca2b0305a0755cae707f2969486674d98761d14b2c79a02a43ba7f5ce26e`).
* **Curated Dataset**: 322 images (241 positive bunches, 81 verified hard-negatives).
* **Held-Out Test Split**: 48 images (36 positive, 12 negative).
* **Held-Out Evaluation Metrics**:
  * **Precision**: 75.61%
  * **Recall**: 72.22%
  * **mAP@50**: 71.55%
  * **mAP@50–95**: 35.27%

### Stage 2: Cavendish Visual Maturity Classifier
* **Model**: Color and texture feature extractor (RGB/HSV histograms, spatial grid statistics, edge/saturation ratios) + `StandardScaler` + Multinomial Logistic Regression.
* **Classes**: `unripe`, `half_ripe`, `ripe`, `overripe`.
* **Output Mapping**: Probability-weighted blend onto the operational 1–7 scale:
  $$\text{Current Maturity} = \sum_{c \in \text{classes}} P(c) \times \text{Anchor}(c)$$
  Anchors: `unripe: 2.0`, `half_ripe: 3.5`, `ripe: 5.5`, `overripe: 6.5`.
* **Artifact**: `models/cavendish_maturity_classifier.joblib` (SHA-256: `117c1f134670ac9b3ebc1b9d3f8a1d81549ec3fbd23f159b741238325f187c9e`).

---

## 2. DAF Biological-Age Context

Days After Flowering ($\text{DAF} = \text{photo\_date} - \text{flowering\_date}$) is computed deterministically as contextual agronomic evidence. In the current MVP, DAF is not fused directly into the logistic scheduling heuristic pending longitudinal field calibration.

---

## 3. Model Artifact Downloads

Pretrained model weights are hosted on GitHub Releases:
* **Release**: [`aic-preliminary-models-v1`](https://github.com/Vluuuu/pisgo/releases/tag/aic-preliminary-models-v1)

Download and place them into `ml/models/`:
```bash
gh release download aic-preliminary-models-v1 --dir models
```
See [`ml/models/README.md`](models/README.md) for checksums and manual download links.

---

## 4. Training & Evaluation Commands

```bash
# Install editable package
pip install -e .

# Run ML unit tests
pytest tests

# Run CV classifier inference on an image
python -m pisgo_ml.cv_predict --config configs/cv_baseline.yaml --image path/to/banana.jpg
```

---

## 5. Historical & Experimental Baselines

The repository preserves historical development modules (such as the tabular Random Forest regressor in `pisgo_ml/train.py` and `pisgo_ml/predict.py`). These represent early experimentation baselines and are not part of the active production runtime.
