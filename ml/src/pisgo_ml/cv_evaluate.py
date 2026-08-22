"""Evaluation metrics for ordered Cavendish maturity classes."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)


def classification_report_metrics(
    y_true: Any,
    y_pred: Any,
    labels: list[str],
) -> dict[str, Any]:
    true = np.asarray(y_true)
    predicted = np.asarray(y_pred)
    per_precision, per_recall, per_f1, per_support = precision_recall_fscore_support(
        true, predicted, labels=labels, average=None, zero_division=0
    )
    macro = precision_recall_fscore_support(
        true, predicted, labels=labels, average="macro", zero_division=0
    )
    weighted = precision_recall_fscore_support(
        true, predicted, labels=labels, average="weighted", zero_division=0
    )
    matrix = confusion_matrix(true, predicted, labels=labels)
    label_to_index = {label: index for index, label in enumerate(labels)}
    ordinal_true = np.asarray([label_to_index[value] for value in true], dtype=float)
    ordinal_pred = np.asarray([label_to_index[value] for value in predicted], dtype=float)

    return {
        "rows": int(len(true)),
        "accuracy": float(accuracy_score(true, predicted)),
        "macro": {
            "precision": float(macro[0]),
            "recall": float(macro[1]),
            "f1": float(macro[2]),
        },
        "weighted": {
            "precision": float(weighted[0]),
            "recall": float(weighted[1]),
            "f1": float(weighted[2]),
        },
        "mean_absolute_class_error": float(np.mean(np.abs(ordinal_true - ordinal_pred))),
        "per_class": {
            label: {
                "precision": float(per_precision[index]),
                "recall": float(per_recall[index]),
                "f1": float(per_f1[index]),
                "support": int(per_support[index]),
            }
            for index, label in enumerate(labels)
        },
        "confusion_matrix": {"labels": labels, "values": matrix.tolist()},
    }
