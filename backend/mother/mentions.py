"""Resolve an explicit leading @recipient before dispatching any model calls."""

import re


def recipient(content, models):
    text = content.lstrip()
    if not text.startswith("@"):
        return None
    matches = []
    for model in models:
        for alias in (model["name"], model["id"]):
            for label in (alias, f'"{alias}"'):
                prefix = "@" + label
                if text.casefold().startswith(prefix.casefold()) and (
                    len(text) == len(prefix) or re.match(r"[\s:,]", text[len(prefix)])
                ):
                    matches.append((len(prefix), model))
    if not matches:
        raise ValueError("Unknown @model. Choose a model from this project's suggestions.")
    length = max(size for size, _ in matches)
    found = {model["id"]: model for size, model in matches if size == length}
    if len(found) != 1:
        raise ValueError("Ambiguous @model name. Use the unique @profile ID instead.")
    model = next(iter(found.values()))
    if not model["enabled"]:
        raise ValueError("This @model is disabled. Enable it in Project setup first.")
    if not text[length:].lstrip(" \t\r\n:,"):
        raise ValueError("Write a message after the @model name.")
    return model["id"]
