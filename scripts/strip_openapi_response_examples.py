#!/usr/bin/env python3
"""
Remove response body `example` / `examples` from OpenAPI so Mintlify Try it
shows live responses without duplicating static JSON in the same panel.

Request bodies and component schemas are unchanged.
"""
from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML


def strip_responses(responses: object) -> None:
    if not isinstance(responses, dict):
        return
    for resp in responses.values():
        if not isinstance(resp, dict):
            continue
        content = resp.get("content")
        if not isinstance(content, dict):
            continue
        for body in content.values():
            if isinstance(body, dict):
                body.pop("example", None)
                body.pop("examples", None)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "api-reference" / "kupe-voice-agent.openapi.yaml"
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    data = y.load(path.read_text())

    for _path_key, path_item in (data.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for _method, op in path_item.items():
            if not isinstance(op, dict) or "responses" not in op:
                continue
            strip_responses(op["responses"])

    for _wh_name, wh_item in (data.get("webhooks") or {}).items():
        if not isinstance(wh_item, dict):
            continue
        for _method, op in wh_item.items():
            if isinstance(op, dict) and "responses" in op:
                strip_responses(op["responses"])

    y.dump(data, path.open("w"))


if __name__ == "__main__":
    main()
