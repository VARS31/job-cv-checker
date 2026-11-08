"""Where the answers to the agents' questions come from: you in the terminal, or a file.

TerminalAnswers (the default): you type each answer.

FileAnswers (python -m orchestrator <ad> <cv> --answers FILE): the answers come from a JSON file, so two
runs (e.g. local and Haiku) get the same answers. Different models find different items unclear and word
them differently, so a yes/no question is matched by the words it contains, never by its id (q1, q2, ...).

File format (example: samples/demo/answers_demo.json):

    {
      "yes_no": {
        "no_if_question_contains": ["Kubernetes"],      <- checked first
        "yes_if_question_contains": ["Python", "SQL"],  <- checked second
        "otherwise": "no"                               <- when nothing matches
      },
      "free_text": "The answer to every free-text question."
    }

Matching ignores upper and lower case. "no" comes first so that a scripted candidate never claims
something by accident.
"""

import json
from pathlib import Path


class TerminalAnswers:
    source = "terminal"

    def yes_no(self, question: str) -> bool:
        while True:
            reply = input(f"   {question} [y/n] ").strip().lower()
            if reply in ("y", "yes", "n", "no"):
                return reply.startswith("y")

    def free_text(self, question: str) -> str:
        print(f"   {question}")
        while not (reply := input("   > ").strip()):
            pass
        return reply


class FileAnswers:
    source = "file"

    def __init__(self, path: Path) -> None:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            rules = data["yes_no"]
            self.no_words = [w.lower() for w in rules.get("no_if_question_contains", [])]
            self.yes_words = [w.lower() for w in rules.get("yes_if_question_contains", [])]
            otherwise = rules["otherwise"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"Can't read the answers file {path}: {type(error).__name__}: {error}") from error
        if otherwise not in ("yes", "no"):
            raise ValueError(f"In {path}, yes_no.otherwise must be \"yes\" or \"no\", not {otherwise!r}.")
        self.otherwise = otherwise == "yes"
        self.text = (data.get("free_text") or "").strip()
        self.path = Path(path)

    def yes_no(self, question: str) -> bool:
        lower = question.lower()
        if any(word in lower for word in self.no_words):
            answer = False
        elif any(word in lower for word in self.yes_words):
            answer = True
        else:
            answer = self.otherwise
        print(f"   {question} [y/n] {'y' if answer else 'n'}   (answers file)")
        return answer

    def free_text(self, question: str) -> str:
        if not self.text:
            raise ValueError(f"The agent asked a free-text question, but {self.path} has no free_text.")
        print(f"   {question}\n   > {self.text}   (answers file)")
        return self.text


def load_answers(path: Path | None):
    """FileAnswers if a file is given, else TerminalAnswers. Raises ValueError for a broken file."""
    return FileAnswers(path) if path is not None else TerminalAnswers()
