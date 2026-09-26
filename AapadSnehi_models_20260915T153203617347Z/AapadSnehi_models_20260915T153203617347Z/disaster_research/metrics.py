from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             confusion_matrix, mean_absolute_error,
                             mean_squared_error, precision_recall_fscore_support,
                             roc_auc_score)


def classification_metrics(y_true, probability, threshold: float = 0.5) -> dict[str, object]:
    y = np.asarray(y_true, dtype=np.int8)
    p = np.clip(np.asarray(probability, dtype=float), 0.0, 1.0)
    if not y.size:
        return {"n":0,"prevalence":None,"threshold":float(threshold),"accuracy":None,"precision":None,"recall":None,"f1":None,"f2":None,"average_precision_sklearn":None,"roc_auc":None,"brier":None,"confusion_matrix_tn_fp_fn_tp":[0,0,0,0],"false_positive_fraction_of_negative_samples":None,"false_negative_samples":0,"false_positive_samples":0,"status":"no_known_targets"}
    pred = p >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(
        y, pred, average="binary", zero_division=0)
    beta2 = 5 * precision * recall / (4 * precision + recall) if (4 * precision + recall) else 0.0
    matrix = confusion_matrix(y, pred, labels=[0, 1])
    return {
        "n": int(y.size), "prevalence": float(y.mean()), "threshold": float(threshold),
        "accuracy": float((pred == y).mean()), "precision": float(precision),
        "recall": float(recall), "f1": float(f1), "f2": float(beta2),
        "average_precision_sklearn": float(average_precision_score(y, p)) if len(np.unique(y)) == 2 else None,
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
        "brier": float(brier_score_loss(y, p)),
        "confusion_matrix_tn_fp_fn_tp": [int(matrix[0, 0]), int(matrix[0, 1]),
                                          int(matrix[1, 0]), int(matrix[1, 1])],
        "false_positive_fraction_of_negative_samples": float(matrix[0, 1] / max(1, matrix[0].sum())),
        "false_negative_samples": int(matrix[1, 0]), "false_positive_samples": int(matrix[0, 1]),
    }


def regression_metrics(y_true, prediction) -> dict[str, float | int | None]:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(prediction, dtype=float)
    if y.shape!=p.shape or not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("Regression evaluation requires aligned finite targets and predictions; rows must not be silently dropped")
    error = p - y
    denominator = np.sum((y - y.mean()) ** 2)
    alpha = np.std(p) / np.std(y) if np.std(y) else np.nan
    beta = np.mean(p) / np.mean(y) if np.mean(y) else np.nan
    correlation = np.corrcoef(y, p)[0, 1] if y.size > 1 and np.std(y) and np.std(p) else np.nan
    kge = 1 - np.sqrt((correlation - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)
    return {"n": int(y.size), "mae": float(mean_absolute_error(y, p)),
            "rmse": float(mean_squared_error(y, p) ** 0.5),
            "nse": float(1 - np.sum(error ** 2) / denominator) if denominator else None,
            "kge": float(kge) if np.isfinite(kge) else None,
            "bias": float(np.mean(error))}


def wildfire_metrics(y_true, probability, current_fire, threshold: float = 0.5) -> dict[str, object]:
    result = classification_metrics(y_true, probability, threshold)
    if result["n"]==0:
        return {**result,"iou":None,"dice":None}
    y = np.asarray(y_true, dtype=bool)
    pred = np.asarray(probability) >= threshold
    intersection = int((y & pred).sum())
    union = int((y | pred).sum())
    result["iou"] = intersection / union if union else 1.0
    result["dice"] = 2 * intersection / (int(y.sum()) + int(pred.sum())) if (y.sum() + pred.sum()) else 1.0
    new_mask = np.asarray(current_fire) == 0
    if new_mask.any():
        nested = classification_metrics(y[new_mask], np.asarray(probability)[new_mask], threshold)
        _,fp,fn,tp=nested["confusion_matrix_tn_fp_fn_tp"]
        nested["iou"]=tp/(tp+fp+fn) if tp+fp+fn else 1.0
        nested["dice"]=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 1.0
        result["newly_active"] = nested
    return result
