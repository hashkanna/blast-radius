from dataclasses import dataclass

from blast_radius.openai_agent import block_text, output_text, to_jsonable


class Block:
    def __init__(self, text: str):
        self.text = text


class ToolOutput:
    blocks = [Block("hello"), Block(" world")]


@dataclass
class Content:
    text: str


@dataclass
class MessageItem:
    type: str
    content: list[Content]


@dataclass
class Response:
    output_text: str | None
    output: list[MessageItem]


class Dumpable:
    def model_dump(self, mode: str):
        return {"mode": mode, "value": 1}


def test_block_text_joins_openreward_blocks() -> None:
    assert block_text(ToolOutput()) == "hello world"


def test_output_text_falls_back_to_message_content() -> None:
    response = Response(
        output_text=None,
        output=[MessageItem(type="message", content=[Content(text="done")])],
    )

    assert output_text(response) == "done"


def test_to_jsonable_handles_pydantic_like_objects() -> None:
    assert to_jsonable({"x": Dumpable()}) == {"x": {"mode": "json", "value": 1}}
