"""Agreement metrics for comparing two label sequences."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class AgreementResult:
    """Agreement metrics between reference and predicted labels."""

    n_samples: int
    accuracy: float
    cohens_kappa: float
    per_label: dict[str, dict[str, float]]


def compute_agreement(labels_a: list[str], labels_b: list[str]) -> AgreementResult:
    """Compute accuracy, Cohen's kappa, and per-label precision/recall/F1."""
    if len(labels_a) != len(labels_b):
        raise ValueError("Label lists must have same length")

    n = len(labels_a)
    if n == 0:
        return AgreementResult(n_samples=0, accuracy=0.0, cohens_kappa=0.0, per_label={})

    labels = sorted(set(labels_a) | set(labels_b))
    matches = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    accuracy = matches / n
    kappa = _cohens_kappa(labels_a, labels_b, labels)

    per_label: dict[str, dict[str, float]] = {}
    for label in labels:
        tp = sum(1 for a, b in zip(labels_a, labels_b) if a == label and b == label)
        fp = sum(1 for a, b in zip(labels_a, labels_b) if a != label and b == label)
        fn = sum(1 for a, b in zip(labels_a, labels_b) if a == label and b != label)

        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1}

    return AgreementResult(
        n_samples=n,
        accuracy=accuracy,
        cohens_kappa=kappa,
        per_label=per_label,
    )


def _cohens_kappa(labels_a: list[str], labels_b: list[str], labels: list[str]) -> float:
    n = len(labels_a)
    if n == 0:
        return 0.0

    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    counts_a = Counter(labels_a)
    counts_b = Counter(labels_b)
    expected = sum(counts_a[label] * counts_b[label] for label in labels) / (n * n)
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)

