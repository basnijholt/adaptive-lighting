from typing import Any

from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
import pandas as pd
import voluptuous as vol

from .const import (
    DOCS,
    DOCS_APPLY,
    DOCS_MANUAL_CONTROL,
    SET_MANUAL_CONTROL_SCHEMA,
    VALIDATION_TUPLES,
    apply_service_schema,
)


def _format_voluptuous_instance(instance):
    coerce_type = None
    min_val = None
    max_val = None

    for validator in instance.validators:
        if isinstance(validator, vol.Coerce):
            coerce_type = validator.type.__name__
        elif isinstance(validator, (vol.Clamp, vol.Range)):
            min_val = validator.min
            max_val = validator.max

    if min_val is not None and max_val is not None:
        return f"`{coerce_type}` {min_val}-{max_val}"
    elif min_val is not None:
        return f"`{coerce_type} > {min_val}`"
    elif max_val is not None:
        return f"`{coerce_type} < {max_val}`"
    else:
        return f"`{coerce_type}`"


def _type_to_str(type_: Any) -> str:
    """Convert a (voluptuous) type to a string."""
    if type_ == cv.entity_ids:
        return "list of `entity_id`s"
    elif type_ in (bool, int, float, str):
        return f"`{type_.__name__}`"
    elif type_ == cv.boolean:
        return "bool"
    elif isinstance(type_, vol.All):
        return _format_voluptuous_instance(type_)
    elif isinstance(type_, vol.In):
        return f"one of `{type_.container}`"
    elif isinstance(type_, selector.SelectSelector):
        return f"one of `{type_.config['options']}`"
    elif isinstance(type_, selector.ColorRGBSelector):
        return "RGB color"
    else:
        raise ValueError(f"Unknown type: {type_}")


def generate_config_markdown_table():
    import pandas as pd

    rows = []
    for k, default, type_ in VALIDATION_TUPLES:
        description = DOCS[k]
        row = {
            "Variable name": f"`{k}`",
            "Description": description,
            "Default": f"`{default}`",
            "Type": _type_to_str(type_),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    return df.to_markdown(index=False)


def _schema_to_dict(schema: vol.Schema) -> dict[str, tuple[Any, Any]]:
    result = {}
    for key, value in schema.schema.items():
        if isinstance(key, vol.Optional):
            default_value = key.default
            result[key.schema] = (default_value, value)
    return result


def _generate_service_markdown_table(
    schema: dict[str, tuple[Any, Any]], alternative_docs: dict[str, str] = None
):
    schema = _schema_to_dict(schema)
    rows = []
    for k, (default, type_) in schema.items():
        if alternative_docs is not None and k in alternative_docs:
            description = alternative_docs[k]
        else:
            description = DOCS[k]
        row = {
            "Service data attribute": f"`{k}`",
            "Description": description,
            "Required": "✅" if default == vol.UNDEFINED else "❌",
            "Type": _type_to_str(type_),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    return df.to_markdown(index=False)


def generate_apply_markdown_table():
    return _generate_service_markdown_table(apply_service_schema(), DOCS_APPLY)


def generate_set_manual_control_markdown_table():
    return _generate_service_markdown_table(
        SET_MANUAL_CONTROL_SCHEMA, DOCS_MANUAL_CONTROL
    )
