# PisGo ML

Workspace untuk dataset, training, evaluation, dan export model AI PisGo.

## Responsibilities

- Cavendish dataset preparation.
- Image annotation.
- YOLO / computer vision experiments.
- Maturity prediction.
- DAF-only, image-only, dan DAF+image comparison.
- Ripening forecast.
- Model evaluation.
- Export model untuk inference service.

## Recommended structure

```text
ml/
├── notebooks/       # exploration / experiments
├── src/             # train, predict, preprocess, evaluate
├── configs/         # model/training configuration
├── datasets/        # metadata only; raw images ignored by git
└── models/          # model notes; large weights ignored by git
```

## Dataset principle

Prioritaskan longitudinal data per plant/bunch dengan field minimum:

```text
image_id
plant_id
bunch_id
flowering_date
photo_date
days_after_flowering
maturity_stage
maturity_score
```

Jangan commit dataset gambar besar atau training runs ke Git biasa.
