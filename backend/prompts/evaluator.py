from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.session import InterviewSession


def build_evaluation_system(session: "InterviewSession") -> str:
    d = session.detection
    return (
        f"You are a senior hiring manager with 15+ years of experience hiring for "
        f"{d.get('industry', 'technology')} roles. "
        f"You have just finished a {d.get('round_type', 'Technical')} interview for a "
        f"{d.get('job_title', 'Software Engineer')} position. "
        f"Evaluate every answer honestly and directly. Do not give undeserved praise. "
        f"If an answer is weak, vague, or missing critical points — say exactly why and what was missing. "
        f"Your feedback must feel like it came from a real senior hiring manager, not a cheerful chatbot. "
        f"Return ONLY a valid JSON object. No markdown, no code fences, no explanation outside the JSON."
    )


def build_evaluation_prompt(session: "InterviewSession") -> str:
    d = session.detection
    job_title = d.get("job_title", "Software Engineer")
    company = d.get("company", "the company")
    round_type = d.get("round_type", "Technical")
    seniority = d.get("seniority", "Mid")
    industry = d.get("industry", "Technology")
    key_skills = ", ".join(d.get("key_skills", [])) or "as per job description"
    tech_stack = ", ".join(d.get("tech_stack", [])) or "not specified"
    resume_summary = d.get("resume_summary", "")
    jd_summary = d.get("jd_summary", "")

    qa_section = _format_qa_pairs(session.conversation_history)

    return f"""Evaluate this {round_type} interview for a {seniority}-level {job_title} position at {company}.

CANDIDATE NAME: {session.candidate_name}
INDUSTRY: {industry}
REQUIRED SKILLS: {key_skills}
TECH STACK: {tech_stack}

CANDIDATE BACKGROUND:
{resume_summary}

ROLE REQUIREMENTS:
{jd_summary}

FULL INTERVIEW TRANSCRIPT:
{qa_section}

Scoring guidelines:
- 9-10: Exceptional. Would impress any interviewer. Specific, structured, insightful.
- 7-8: Good. Solid answer with minor gaps in depth or specificity.
- 5-6: Adequate but underwhelming. Vague, generic, or missing key elements.
- 3-4: Weak. Significant gaps, poor structure, or irrelevant content.
- 1-2: Very poor. Non-answer, clearly unprepared, or factually wrong.

IMPORTANT: Only evaluate answers that were actually given by the candidate. If an answer is empty, missing, or less than 10 words, mark that question as 'Not answered' and give a score of 0. Never invent or assume answers. Never generate feedback for questions that were not answered.

CRITICAL FORMATTING RULES:
- "strengths", "improvements", and "recommended_study" MUST each be an array of PLAIN STRINGS.
- Do NOT use objects/dictionaries inside these arrays. Never write {{"area": "...", "tip": "..."}}.
- Each improvement is ONE complete sentence written as a string, e.g.:
  "improvements": [
    "Work on structuring answers using the STAR format more consistently",
    "Provide more specific metrics and outcomes in your examples",
    "Research the company's tech stack before the interview"
  ]
- WRONG (never do this): "improvements": [{{"area": "STAR format", "tip": "..."}}]

Return ONLY this JSON (no other text):
{{
  "overall_score": <float 1.0-10.0, one decimal place>,
  "verdict": "<exactly one of: Interview Ready | Almost Ready - 2-3 weeks of prep | Needs Significant Preparation>",
  "strengths": [
    "<specific strength 1 as a plain string — reference actual answers, not generic praise>",
    "<specific strength 2 as a plain string>",
    "<specific strength 3 as a plain string>"
  ],
  "improvements": [
    "<specific improvement 1 as a plain string with a concrete action item>",
    "<specific improvement 2 as a plain string with a concrete action item>",
    "<specific improvement 3 as a plain string with a concrete action item>"
  ],
  "recommended_study": [
    "<topic or resource 1 as a plain string>",
    "<topic or resource 2 as a plain string>",
    "<topic or resource 3 as a plain string>"
  ],
  "per_answer": [
    {{
      "question": "<the interviewer question>",
      "candidate_answer": "<what the candidate said>",
      "score": <int 1-10>,
      "strong_points": ["<what was genuinely good>"],
      "weak_points": ["<what was missing, vague, or wrong — be specific>"],
      "ideal_answer": "<a concrete example of what an excellent answer looks like for this question at this seniority level>",
      "missing_keywords": ["<important concept, term, or framework they never mentioned>"]
    }}
  ],
  "dimension_scores": {{
    "communication": <int 1-10>,
    "technical_depth": <int 1-10>,
    "structured_thinking": <int 1-10>,
    "confidence": <int 1-10>,
    "role_relevance": <int 1-10>
  }}
}}"""


def _format_qa_pairs(history: list) -> str:
    if not history:
        return "No questions and answers recorded."
    lines = []
    for i, qa in enumerate(history, 1):
        q = qa.get("question", "").strip()
        a = qa.get("answer", "").strip()
        lines.append(f"Q{i}: {q}\nA{i}: {a}\n")
    return "\n".join(lines)
