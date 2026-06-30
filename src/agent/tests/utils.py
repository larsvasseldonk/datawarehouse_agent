from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


def collect_tools(messages):
    tool_calls = []

    for m in messages:
        for p in m.parts:
            part_kind = p.part_kind

            if part_kind != 'tool-call':
                continue

            if p.tool_name == 'final_result':
                continue

            tool_calls.append(ToolCall(p.tool_name, p.args))

    return tool_calls
