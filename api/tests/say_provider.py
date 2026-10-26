"""A language model for Say it in English's tests: it answers each kind of prompt the way
the real one would, from replies the test sets, and can be made to fail one kind."""

import json

from services.llm import LlmUnavailable
from tests.conftest import StubProvider

DIRECT = (
    "Laura, I'm writing to let you know that the client report is going to be delayed "
    "until Thursday the 14th, because we are still waiting for Acme's data."
)
ORGANIZED = (
    "Hi Laura,\n\nA quick heads-up: the client report will be delayed until Thursday the "
    "14th, as we're still waiting for Acme's data."
)
POLISHED = "I received your message and will call you tomorrow morning."


class SayProvider(StubProvider):
    """Replies by what the prompt asks for: a version, error labels, or phrases."""

    def __init__(self) -> None:
        super().__init__(model="gemma4:e4b")
        self.replies_by_kind = {
            "direct": DIRECT,
            "organized": ORGANIZED,
            "polished": POLISHED,
            "errors": {"errors": []},
            "phrases": {
                "phrases": [
                    {
                        "source": "te escribo para avisarte",
                        "english": "a quick heads-up",
                    },
                    {"source": "se va a retrasar", "english": "will be delayed"},
                    # Invented on both sides: neither half is in the texts.
                    {"source": "por favor", "english": "please"},
                ]
            },
        }
        self.down: set[str] = set()
        self.kinds: list[str] = []
        self.warmed = 0

    @staticmethod
    def kind_of(messages) -> str:
        system = messages[0].content
        if system.startswith("You translate"):
            return "direct"
        if system.startswith("You write in English"):
            return "organized"
        if system.startswith("You improve"):
            return "polished"
        if system.startswith("You are marking"):
            return "errors"
        return "phrases"

    async def complete(self, messages, max_tokens=None, temperature=None):
        self.calls.append(messages)
        self.temperatures.append(temperature)
        kind = self.kind_of(messages)
        self.kinds.append(kind)
        if kind in self.down:
            raise LlmUnavailable("ConnectError: [Errno 111] refused")
        reply = self.replies_by_kind[kind]
        return self._completion(
            messages, reply if isinstance(reply, str) else json.dumps(reply)
        )

    async def warm(self) -> None:
        self.warmed += 1
