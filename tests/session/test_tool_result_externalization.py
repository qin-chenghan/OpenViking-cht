# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

import json

from openviking.message import ToolPart
from openviking.server.config import ToolOutputExternalizationConfig
from openviking.session import Session
from openviking.session.tool_result_store import ToolResultStore


def _small_config(**overrides):
    values = {
        "threshold_chars": 20,
        "preview_chars": 12,
        "assistant_turn_inline_budget_chars": 30,
        "assistant_turn_preview_budget_chars": 20,
        "min_preview_chars": 4,
    }
    values.update(overrides)
    return ToolOutputExternalizationConfig(**values)


async def test_add_message_externalizes_large_tool_output(session: Session):
    session._tool_output_externalization_config = _small_config()
    raw = "alpha-" * 20

    msg = session.add_message(
        "user",
        [
            ToolPart(
                tool_id="call_1",
                tool_name="read_file",
                tool_input={"path": "a.txt"},
                tool_output=raw,
                tool_status="completed",
            )
        ],
    )

    part = msg.get_tool_parts()[0]
    assert part.tool_output_truncated is True
    assert part.tool_output_ref.startswith(f"viking://session/{session.session_id}/tool-results/")
    assert part.tool_output_original_chars == len(raw)
    assert part.tool_output_externalized_reason == "single_threshold"
    assert raw not in part.tool_output

    stored = await session.read_tool_result(part.tool_output_ref.rsplit("/", 1)[-1], limit=-1)
    assert stored["content"] == raw
    assert stored["offset_unit"] == "unicode_code_point"


async def test_assistant_turn_budget_externalizes_largest_medium_output(session: Session):
    session._tool_output_externalization_config = _small_config(
        threshold_chars=100,
        assistant_turn_inline_budget_chars=25,
    )

    msg = session.add_message(
        "user",
        [
            ToolPart(
                tool_id="call_a",
                tool_name="tool_a",
                tool_output="a" * 18,
                tool_status="completed",
            ),
            ToolPart(
                tool_id="call_b",
                tool_name="tool_b",
                tool_output="b" * 12,
                tool_status="completed",
            ),
        ],
    )

    parts = msg.get_tool_parts()
    externalized = [p for p in parts if p.tool_output_truncated]
    assert len(externalized) == 1
    assert externalized[0].tool_id == "call_a"
    assert externalized[0].tool_output_externalized_reason == "turn_budget"
    assert all(p.tool_output_group_original_chars == 30 for p in parts)


async def test_read_back_tool_result_reuses_source_ref(session: Session):
    session._tool_output_externalization_config = _small_config()
    raw = "source-" * 20
    original = session.add_message(
        "user",
        [
            ToolPart(
                tool_id="call_src",
                tool_name="read_file",
                tool_output=raw,
                tool_status="completed",
            )
        ],
    ).get_tool_parts()[0]

    read_msg = session.add_message(
        "user",
        [
            ToolPart(
                tool_id="call_read",
                tool_name="openviking_tool_result_read",
                tool_input={"tool_output_ref": original.tool_output_ref, "offset": 0, "limit": 50},
                tool_output=raw[:50],
                tool_status="completed",
            )
        ],
    )

    read_part = read_msg.get_tool_parts()[0]
    assert read_part.tool_output_ref == original.tool_output_ref
    assert read_part.tool_output_source_ref == original.tool_output_ref
    assert read_part.tool_output_source_offset == 0
    assert read_part.tool_output_source_limit == 50
    assert read_part.tool_output_externalized_reason == "source_read"


async def test_update_tool_part_externalizes_large_output(session_with_tool_call):
    session, message_id, tool_id = session_with_tool_call
    session._tool_output_externalization_config = _small_config()
    raw = "updated-" * 20

    session.update_tool_part(message_id, tool_id, raw, status="completed")

    msg = next(m for m in session.messages if m.id == message_id)
    part = msg.find_tool_part(tool_id)
    assert part is not None
    assert part.tool_output_truncated is True
    assert part.tool_output_ref
    stored = await session.read_tool_result(part.tool_output_ref.rsplit("/", 1)[-1], limit=-1)
    assert stored["content"] == raw


async def test_list_tool_results_filters_tool_name_before_limit():
    class FakeVikingFS:
        def __init__(self):
            self.entries = [
                {"name": "tr_other", "isDir": True},
                {"name": "tr_target", "isDir": True},
            ]
            self.metadata = {
                "tr_other": {"tool_result_id": "tr_other", "tool_name": "other"},
                "tr_target": {"tool_result_id": "tr_target", "tool_name": "target"},
            }

        async def ls(self, uri, *, output, node_limit, ctx):  # noqa: ANN001
            return self.entries[:node_limit]

        async def read_file(self, uri, *, ctx):  # noqa: ANN001
            tool_result_id = uri.rstrip("/").split("/")[-2]
            return json.dumps(self.metadata[tool_result_id])

    store = ToolResultStore(
        FakeVikingFS(),
        "viking://session/filter-before-limit",
        "filter-before-limit",
        ctx=None,
    )

    result = await store.list(tool_name="target", limit=1)

    assert result["tool_results"] == [{"tool_result_id": "tr_target", "tool_name": "target"}]
