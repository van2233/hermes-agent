"""Bound the aggregate JSON shape. This does not fetch it."""

from __future__ import annotations

from dataclasses import dataclass

_MAX_ROWS = 500
_MAX_LABEL = 200
_MAX_DIMS = 4
_MAX_MEASURES = 8


class EmptyAggregate(ValueError):
    pass


class PayloadBoundsError(ValueError):
    pass


@dataclass(frozen=True)
class ChartTable:
    labels: tuple[str, ...]
    values: tuple[float, ...]
    dimension: str
    measure: str


def parse_aggregate(payload: dict) -> ChartTable:
    if not isinstance(payload, dict):
        raise PayloadBoundsError("payload")
    dimensions = payload.get("dimensions")
    measures = payload.get("measures")
    rows = payload.get("main_data")
    if not isinstance(dimensions, list) or not isinstance(measures, list) or not isinstance(rows, list):
        raise PayloadBoundsError("shape")
    if len(dimensions) > _MAX_DIMS or len(measures) > _MAX_MEASURES or len(rows) > _MAX_ROWS:
        raise PayloadBoundsError("size")
    if not dimensions or not measures:
        raise PayloadBoundsError("shape")
    if not rows:
        raise EmptyAggregate("main_data empty")
    dim_alias = _alias(dimensions[0])
    measure_alias = _alias(measures[0])
    labels = []
    values = []
    for row in rows:
        if not isinstance(row, dict):
            raise PayloadBoundsError("row")
        label = row.get(dim_alias, "")
        if not isinstance(label, str) or len(label) > _MAX_LABEL:
            raise PayloadBoundsError("label")
        number = row.get(measure_alias)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise PayloadBoundsError("measure")
        labels.append(label)
        values.append(float(number))
    return ChartTable(
        labels=tuple(labels), values=tuple(values),
        dimension=str(dimensions[0].get("field_name") or "")[:_MAX_LABEL],
        measure=str(measures[0].get("field_name") or "")[:_MAX_LABEL],
    )


def _alias(item) -> str:
    if not isinstance(item, dict):
        raise PayloadBoundsError("column")
    alias = item.get("alias")
    if not isinstance(alias, str) or not alias or len(alias) > 80:
        raise PayloadBoundsError("alias")
    return alias
