def build_detection_prompt(resume_text: str, jd_text: str, job_role: str = "") -> str:
    resume_excerpt = resume_text[:3000] if resume_text else "No resume provided"
    jd_excerpt = jd_text[:3000] if jd_text else "No job description provided"
    role_hint = f"\nThe user indicated the role is: {job_role}" if job_role else ""

    return f"""Analyze the resume and job description below. Extract structured information and return ONLY a valid JSON object — no markdown, no explanation, no code fences.

RESUME:
{resume_excerpt}

JOB DESCRIPTION:
{jd_excerpt}{role_hint}

Return this exact JSON structure (all fields required):
{{
  "job_title": "exact job title from JD or best inference",
  "company": "company name from JD, or 'the company' if unknown",
  "industry": "one of: Technology, Finance, Healthcare, Legal, Marketing, Sales, Design, Data Science, Product Management, Consulting, Engineering, Education, Government, Retail, Media, Real Estate, Manufacturing, HR, Operations",
  "seniority": "one of: Intern, Entry, Mid, Senior, Lead, Manager, Director, VP, C-Suite",
  "round_type": "one of: Screening, Technical, Behavioral, HR, Final",
  "tech_stack": ["array", "of", "specific", "technologies", "from", "JD"],
  "key_skills": ["array", "of", "top", "5-8", "required", "skills"],
  "resume_summary": "2-3 sentence factual summary of candidate background and experience",
  "jd_summary": "2-3 sentence summary of what this role requires and entails",
  "gap_analysis": "Specific skills, experience, or qualifications the candidate appears to lack relative to the JD requirements",
  "interviewer_name": "a realistic American first and last name",
  "interviewer_title": "a realistic professional title matching the round (e.g. 'Senior Engineering Manager' for Technical, 'HR Business Partner' for HR round)",
  "interview_style": "one of: warm, formal, technical, casual"
}}

Round selection logic:
- Entry/Intern + any role → Screening
- Mid/Senior + Software/Data/Engineering → Technical
- Any level + HR/Operations/People roles → HR
- Lead/Manager/Director + any → Behavioral
- VP/C-Suite + any → Final
- Override with Technical if JD is heavily technical regardless of seniority

Return ONLY the JSON object."""
