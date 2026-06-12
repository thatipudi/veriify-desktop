from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sessions: Dict[str, "InterviewSession"] = {}


@dataclass
class InterviewSession:
    session_id: str
    candidate_name: str
    resume_text: str
    jd_text: str
    detection: Dict[str, Any]

    messages: List[Dict[str, str]] = field(default_factory=list)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)

    question_count: int = 0
    max_questions: int = 10
    status: str = "setup"  # setup | active | closing | ended | evaluating
    evaluation: Optional[Dict[str, Any]] = None

    def record_answer(self, answer: str) -> None:
        last_question = ""
        for msg in reversed(self.messages):
            if msg["role"] == "assistant":
                last_question = msg["content"]
                break

        self.conversation_history.append(
            {
                "question": last_question,
                "answer": answer,
                "question_number": self.question_count,
            }
        )
