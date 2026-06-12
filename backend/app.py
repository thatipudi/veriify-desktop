import asyncio
import base64
import io
import json
import os
import re
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from prompts.detector import build_detection_prompt
from prompts.evaluator import build_evaluation_prompt, build_evaluation_system
from prompts.interviewer import build_interviewer_system_prompt, build_opening_prompt, build_wrap_up_note
from utils.parser import extract_text
from utils.session import InterviewSession, sessions
from utils import database as authdb
from utils.email import send_welcome_email

# When running as a frozen PyInstaller binary, data files bundled via
# --add-data (static/, prompts/, utils/, optionally models/) are unpacked to
# sys._MEIPASS. Switch the working directory there so the relative paths below
# (StaticFiles directory, static/index.html, models/) resolve correctly.
import sys

if getattr(sys, "frozen", False):
    os.chdir(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))

app = FastAPI(title="Mock Interview Coach")
app.mount("/static", StaticFiles(directory="static"), name="static")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1:8b"


@app.get("/")
async def root():
    return HTMLResponse(Path("static/index.html").read_text(encoding="utf-8"))


@app.post("/api/analyze")
async def analyze_documents(
    candidate_name: str = Form(...),
    job_role: str = Form(""),
    resume: UploadFile = File(...),
    jd_text: str = Form(""),
    jd_file: UploadFile = File(None),
):
    resume_content = await extract_text(resume)

    jd_content = jd_text.strip()
    if jd_file and jd_file.filename:
        extracted = await extract_text(jd_file)
        if extracted and not extracted.startswith("["):
            jd_content = extracted

    if not jd_content:
        return {"error": "Please provide a job description (paste text or upload a file)."}
    if not resume_content or resume_content.startswith("["):
        return {"error": f"Could not read resume: {resume_content}"}

    detection = await _detect_context(resume_content, jd_content, job_role)

    session_id = str(uuid.uuid4())
    sessions[session_id] = InterviewSession(
        session_id=session_id,
        candidate_name=candidate_name.strip(),
        resume_text=resume_content,
        jd_text=jd_content,
        detection=detection,
    )

    # Fire-and-forget: load model into GPU/RAM while user reads detection results
    asyncio.create_task(_prewarm_model())

    return {"session_id": session_id, "detection": detection}


@app.post("/api/update-round")
async def update_round(session_id: str = Form(...), round_type: str = Form(...)):
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    session.detection["round_type"] = round_type
    return {"ok": True}


@app.websocket("/ws/{session_id}")
async def websocket_interview(websocket: WebSocket, session_id: str):
    await websocket.accept()

    session = sessions.get(session_id)
    if not session:
        await websocket.send_json({"type": "error", "message": "Session not found — please restart."})
        await websocket.close()
        return

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            if msg_type == "start_interview":
                await _handle_start(websocket, session)

            elif msg_type == "candidate_answer":
                answer = data.get("answer", "").strip()
                if not answer:
                    await websocket.send_json({"type": "prompt_answer"})
                    continue
                session.record_answer(answer)
                await _handle_next_turn(websocket, session)

            elif msg_type == "candidate_question":
                cq = data.get("question", "").strip()
                user_msg = cq if cq else "No, I don't have any questions. Thank you."
                session.messages.append({"role": "user", "content": user_msg})
                await _stream_response(websocket, session, is_final=True)
                session.status = "ended"

            elif msg_type == "end_interview":
                await _handle_evaluation(websocket, session)
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": f"Server error: {e}"})
        except Exception:
            pass


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _detect_context(resume_text: str, jd_text: str, job_role: str) -> dict:
    prompt = build_detection_prompt(resume_text, jd_text, job_role)
    system = (
        "You are an expert HR analyst. Analyze the documents carefully and return ONLY a valid JSON object. "
        "No markdown, no code fences, no explanation — just the raw JSON."
    )
    raw = await _ollama_complete(prompt, system, temperature=0.15, num_ctx=4096)
    result = _parse_json(raw)

    if not result or "job_title" not in result:
        result = _fallback_detection(job_role)

    return result


def _fallback_detection(job_role: str) -> dict:
    return {
        "job_title": job_role or "Software Engineer",
        "company": "the company",
        "industry": "Technology",
        "seniority": "Mid",
        "round_type": "Technical",
        "tech_stack": [],
        "key_skills": [],
        "resume_summary": "Candidate background could not be parsed.",
        "jd_summary": "Job requirements could not be parsed.",
        "gap_analysis": "Review the job description requirements carefully.",
        "interviewer_name": "Alex Rivera",
        "interviewer_title": "Senior Hiring Manager",
        "interview_style": "professional",
    }


async def _handle_start(websocket: WebSocket, session: InterviewSession) -> None:
    session.status = "active"
    system_prompt = build_interviewer_system_prompt(session)
    opening_prompt = build_opening_prompt(session)

    session.messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": opening_prompt},
    ]

    await _stream_response(websocket, session)
    session.question_count = 1


async def _handle_next_turn(websocket: WebSocket, session: InterviewSession) -> None:
    last_answer = session.conversation_history[-1]["answer"]
    is_last = session.question_count >= session.max_questions

    if is_last:
        combined = last_answer + build_wrap_up_note(session.question_count, session.max_questions)
        session.messages.append({"role": "user", "content": combined})
        session.status = "closing"
    else:
        session.messages.append({"role": "user", "content": last_answer})

    await _stream_response(websocket, session, is_closing=is_last)

    if not is_last:
        session.question_count += 1


async def _stream_response(
    websocket: WebSocket,
    session: InterviewSession,
    is_closing: bool = False,
    is_final: bool = False,
) -> None:
    await websocket.send_json({"type": "interviewer_start"})

    full_text = ""
    try:
        async for chunk in _stream_ollama(session.messages):
            full_text += chunk
            await websocket.send_json({"type": "interviewer_chunk", "content": chunk})
    except Exception as e:
        await websocket.send_json({"type": "interviewer_chunk", "content": f"\n[Error: {e}]"})

    if not full_text.strip():
        full_text = "I apologize, I had a moment of difficulty. Could you repeat or rephrase your last answer?"

    session.messages.append({"role": "assistant", "content": full_text})

    await websocket.send_json(
        {
            "type": "interviewer_done",
            "question_count": session.question_count,
            "max_questions": session.max_questions,
            "is_closing": is_closing,
            "is_final": is_final,
        }
    )


async def _handle_evaluation(websocket: WebSocket, session: InterviewSession) -> None:
    session.status = "evaluating"
    await websocket.send_json({"type": "evaluating"})

    prompt = build_evaluation_prompt(session)
    system = build_evaluation_system(session)
    raw = await _ollama_complete(prompt, system, temperature=0.2, num_ctx=8192)
    evaluation = _parse_json(raw)

    if not evaluation or "overall_score" not in evaluation:
        evaluation = _fallback_evaluation(session)

    session.evaluation = evaluation
    await websocket.send_json({"type": "evaluation_complete", "evaluation": evaluation})


async def _ollama_complete(
    prompt: str, system: str, temperature: float = 0.3, num_ctx: int = 4096
) -> str:
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {"temperature": temperature, "top_p": 0.9, "num_ctx": num_ctx},
                },
            )
            return resp.json().get("message", {}).get("content", "")
    except Exception as e:
        return f"[Ollama error: {e}]"


async def _stream_ollama(messages: list, temperature: float = 0.72):
    trimmed = _trim_messages(messages)
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": trimmed,
                    "stream": True,
                    "keep_alive": "10m",
                    "options": {"temperature": temperature, "top_p": 0.9, "num_ctx": 8192},
                },
            ) as response:
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("done"):
                            return
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        yield f"\n[Connection error: {e}]"


def _trim_messages(messages: list, max_chars: int = 20000) -> list:
    """Keep system prompt + as many recent messages as fit within max_chars.
    Prevents context overflow on long interviews with verbose answers."""
    if not messages:
        return messages

    system = [m for m in messages if m["role"] == "system"]
    rest = [m for m in messages if m["role"] != "system"]

    total = sum(len(m.get("content", "")) for m in system)

    # Walk backwards, keeping recent messages first
    kept = []
    for msg in reversed(rest):
        msg_len = len(msg.get("content", ""))
        if total + msg_len > max_chars and kept:
            break
        kept.append(msg)
        total += msg_len

    kept.reverse()
    return system + kept


async def _prewarm_model() -> None:
    """Load the model into memory so the first interview response is fast.
    Called as a background task right after /api/analyze returns."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {"num_predict": 1, "num_ctx": 512},
                },
            )
    except Exception:
        pass


def _parse_json(text: str) -> dict:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        return {}
    json_str = text[start:end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}


def _fallback_evaluation(session: InterviewSession) -> dict:
    return {
        "overall_score": 6.0,
        "verdict": "Almost Ready - 2-3 weeks of prep",
        "strengths": [
            "Completed the full interview and engaged with all questions",
            "Demonstrated genuine interest in the role",
            "Showed willingness to reflect on past experiences",
        ],
        "improvements": [
            "Use the STAR method for every behavioral answer: Situation → Task → Action → Result",
            "Prepare 5-7 specific stories from past work with measurable outcomes",
            "Research the company, its products, and the industry deeply before the real interview",
        ],
        "recommended_study": [
            "STAR method for behavioral interview answers",
            f"{session.detection.get('job_title', 'role')}-specific technical concepts",
            "Company research: mission, products, recent news, competitors",
        ],
        "per_answer": [
            {
                "question": qa.get("question", ""),
                "candidate_answer": qa.get("answer", ""),
                "score": 6,
                "strong_points": ["Attempted to answer the question"],
                "weak_points": ["Could provide more specific examples with measurable outcomes"],
                "ideal_answer": "A strong answer includes specific context, your individual actions, and a quantifiable result.",
                "missing_keywords": [],
            }
            for qa in session.conversation_history
        ],
        "dimension_scores": {
            "communication": 6,
            "technical_depth": 6,
            "structured_thinking": 6,
            "confidence": 6,
            "role_relevance": 6,
        },
    }


# ── Voice endpoints ───────────────────────────────────────────────────────────

# ── Whisper (transcription) ───────────────────────────────────────────────────
_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _whisper_model


# ── Kokoro ONNX (TTS) ─────────────────────────────────────────────────────────
_MODELS_DIR = Path(__file__).parent / "models"
_KOKORO_MODEL_PATH = str(_MODELS_DIR / "kokoro-v1.0.onnx")
_KOKORO_VOICES_PATH = str(_MODELS_DIR / "voices-v1.0.bin")

_kokoro: object = None
_kokoro_lock = threading.Lock()
_kokoro_ready = False
_kokoro_error: str | None = None


def _init_kokoro_sync():
    global _kokoro, _kokoro_ready, _kokoro_error
    with _kokoro_lock:
        if _kokoro is not None:
            return _kokoro
        try:
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(_KOKORO_MODEL_PATH, _KOKORO_VOICES_PATH)
            _kokoro_ready = True
            _kokoro_error = None
        except Exception as exc:
            _kokoro_ready = False
            _kokoro_error = str(exc)
    return _kokoro


# Best Kokoro voice for a warm, confident, professional female interviewer.
KOKORO_VOICE = "af_heart"        # Primary
KOKORO_FALLBACK_VOICE = "af_sarah"  # If the requested voice is unavailable
KOKORO_SPEED = 0.88              # Slightly slower = more deliberate, confident pacing


def _generate_kokoro_wav(text: str, voice: str = KOKORO_VOICE, speed: float = KOKORO_SPEED) -> bytes:
    import soundfile as sf

    pipeline = _init_kokoro_sync()
    if pipeline is None:
        raise RuntimeError(f"Kokoro unavailable: {_kokoro_error}")

    try:
        samples, sample_rate = pipeline.create(text, voice=voice, speed=speed, lang="en-us")
    except Exception:
        # Fall back to a known-good voice rather than failing the sentence outright.
        samples, sample_rate = pipeline.create(
            text, voice=KOKORO_FALLBACK_VOICE, speed=speed, lang="en-us"
        )

    buf = io.BytesIO()
    sf.write(buf, samples, samplerate=sample_rate, format="WAV", subtype="FLOAT")
    buf.seek(0)
    return buf.read()


@app.on_event("startup")
async def _startup():
    async def _warm():
        await asyncio.to_thread(_init_kokoro_sync)
        # Pre-warm the pipeline so the first real response has no cold-start delay.
        try:
            await asyncio.to_thread(_generate_kokoro_wav, "Hello.", KOKORO_VOICE, KOKORO_SPEED)
            print("✅ Kokoro voice engine ready")
        except Exception as e:
            print(f"⚠️ Kokoro warmup failed: {e}")

    asyncio.create_task(_warm())


@app.on_event("startup")
async def _startup_db():
    # Initialize the auth database. Kept resilient: if Postgres isn't running,
    # the core interview app still boots (auth endpoints will report errors).
    try:
        await asyncio.to_thread(authdb.init_db)
        print("✅ Database connected")
    except Exception as e:
        print(f"❌ Database error: {e}")
        print("Run: brew services start postgresql@17")
        print("Then: python setup_db.py")


# ── Auth ──────────────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/signup")
async def signup(request: SignupRequest):
    # Validate (outside the try so these 400s aren't masked by the ValueError handler)
    if len(request.name.strip()) < 2:
        raise HTTPException(400, "Name too short")
    if len(request.password) < 8:
        raise HTTPException(400, "Password must be 8+ characters")
    if "@" not in request.email:
        raise HTTPException(400, "Invalid email")

    try:
        user = await asyncio.to_thread(
            authdb.create_user,
            request.name.strip(),
            request.email.lower().strip(),
            request.password,
        )
        token = await asyncio.to_thread(authdb.create_session, user["id"])
    except ConnectionError:
        raise HTTPException(503, "Database unavailable. Please try again.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        print(f"Signup error: {e}")
        raise HTTPException(500, f"Signup failed: {e}")

    # Send welcome email (non-blocking; failures are logged, never block signup)
    asyncio.create_task(asyncio.to_thread(send_welcome_email, user["name"], user["email"]))

    return {
        "success": True,
        "token": token,
        "user": {"name": user["name"], "email": user["email"]},
    }


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    try:
        user = await asyncio.to_thread(
            authdb.verify_login,
            request.email.lower().strip(),
            request.password,
        )
        token = await asyncio.to_thread(authdb.create_session, user["id"])
    except ConnectionError:
        raise HTTPException(503, "Database unavailable. Please try again.")
    except ValueError as e:
        raise HTTPException(401, str(e))
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(500, f"Login failed: {e}")

    return {
        "success": True,
        "token": token,
        "user": {
            "name": user["name"],
            "email": user["email"],
            "interview_count": user["interview_count"],
        },
    }


@app.get("/api/auth/verify")
async def verify_token(token: str):
    try:
        user = await asyncio.to_thread(authdb.verify_session, token)
        return {"success": True, "user": user}
    except ValueError:
        raise HTTPException(401, "Invalid session")
    except Exception:
        raise HTTPException(401, "Invalid session")


@app.post("/api/auth/logout")
async def logout(token: str = Form(...)):
    try:
        await asyncio.to_thread(authdb.delete_session, token)
    except Exception:
        pass
    return {"success": True}


# ── Interview history ─────────────────────────────────────────────────────────
class SaveInterviewRequest(BaseModel):
    token: str
    role: str = ""
    company: str = ""
    round_type: str = ""
    interviewer_name: str = ""
    interviewer_title: str = ""
    overall_score: float = 0.0
    verdict: str = ""
    report: dict | None = None


@app.post("/api/history/save")
async def history_save(req: SaveInterviewRequest):
    try:
        user = await asyncio.to_thread(authdb.verify_session, req.token)
    except ValueError:
        raise HTTPException(401, "Invalid session")

    try:
        await asyncio.to_thread(
            authdb.save_interview,
            user["id"],
            (req.role or "")[:255],
            (req.company or "")[:255],
            (req.round_type or "")[:100],
            float(req.overall_score or 0),
            (req.verdict or "")[:100],
            req.report or {},
            (req.interviewer_name or "")[:255],
            (req.interviewer_title or "")[:255],
        )
    except Exception as e:
        raise HTTPException(500, f"Could not save interview: {e}")

    return {"success": True}


@app.get("/api/history")
async def history_list(token: str):
    try:
        user = await asyncio.to_thread(authdb.verify_session, token)
    except ValueError:
        raise HTTPException(401, "Invalid session")

    rows = await asyncio.to_thread(authdb.get_interview_history, user["id"])
    return {"success": True, "interviews": rows}


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe audio blob using faster-whisper (base.en model)."""
    content = await audio.read()
    filename = audio.filename or "recording.webm"
    suffix = os.path.splitext(filename)[1] or ".webm"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        model = _get_whisper_model()
        segments, _ = model.transcribe(tmp_path, language="en", beam_size=1, vad_filter=True)
        transcript = " ".join(seg.text.strip() for seg in segments).strip()
        return {"transcript": transcript}

    except ImportError:
        return {"transcript": "", "error": "faster-whisper not installed — run: pip install faster-whisper"}
    except Exception as e:
        return {"transcript": "", "error": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.get("/api/voice/status")
async def voice_status():
    return {"ready": _kokoro_ready, "error": _kokoro_error}


_CONTRACTIONS = {
    "I am": "I'm", "you are": "you're", "we are": "we're",
    "they are": "they're", "it is": "it's", "that is": "that's",
    "what is": "what's", "how is": "how's", "do not": "don't",
    "does not": "doesn't", "did not": "didn't", "cannot": "can't",
    "will not": "won't", "would not": "wouldn't", "could not": "couldn't",
    "should not": "shouldn't", "I would": "I'd", "I will": "I'll",
    "let us": "let's", "that would": "that'd",
}

_FILLER_WORDS = [
    "Well", "So", "Now", "Right", "Actually", "Honestly", "Essentially",
    "Basically", "Great", "Interesting", "Got it", "I see",
]


def _humanize_text(text: str) -> str:
    """Make text read more like natural speech: contractions + breathing pauses."""
    # Expand formal phrasing into contractions (sounds more human).
    for formal, casual in _CONTRACTIONS.items():
        text = re.sub(r"\b" + re.escape(formal) + r"\b", casual, text, flags=re.IGNORECASE)

    # Add a natural pause (comma) after leading filler words.
    for word in _FILLER_WORDS:
        text = re.sub(rf"\b{re.escape(word)}\b(?!,)", f"{word},", text)

    # Em-dashes and ellipses become soft pauses.
    text = text.replace("—", ", ").replace("...", ", ").replace("…", ", ")

    # Collapse any doubled commas / whitespace the steps above may have introduced.
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_pause_after_sentence(sentence: str) -> float:
    """Human-like pause (seconds) to insert after a spoken sentence."""
    sentence = sentence.strip()
    if sentence.endswith("?"):
        return 0.6   # Questions invite a beat of reflection.
    if sentence.endswith("!"):
        return 0.4
    if len(sentence) < 60:
        return 0.25
    return 0.35


@app.post("/api/speak")
async def speak_text(request: Request):
    """Stream sentence-by-sentence Kokoro TTS as NDJSON for natural, human pacing.

    Each line is a JSON object: {"audio": <base64 wav>, "sentence": str, "pause": float}.
    The client plays each sentence with a short fade-in and the given pause between them.
    """
    body = await request.json()
    raw_text = body.get("text", "").strip()
    voice = body.get("voice") or KOKORO_VOICE
    speed = float(body.get("speed", KOKORO_SPEED))

    if not raw_text:
        return Response(status_code=400, content=b"No text provided")

    text = _humanize_text(_clean_for_tts(raw_text))
    if not text:
        return Response(status_code=204)

    # If the engine isn't available, signal failure so the client uses browser TTS.
    if _init_kokoro_sync() is None:
        return Response(status_code=503, content=b"TTS unavailable")

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 3]
    if not sentences:
        sentences = [text]
    # Re-capitalise sentence starts (contraction expansion can lowercase the first word).
    sentences = [s[:1].upper() + s[1:] for s in sentences]

    async def generate_audio():
        for sentence in sentences:
            try:
                wav_bytes = await asyncio.to_thread(_generate_kokoro_wav, sentence, voice, speed)
            except Exception:
                continue
            if not wav_bytes:
                continue
            chunk = json.dumps({
                "audio": base64.b64encode(wav_bytes).decode("ascii"),
                "sentence": sentence,
                "pause": _get_pause_after_sentence(sentence),
            }) + "\n"
            yield chunk.encode("utf-8")

    return StreamingResponse(generate_audio(), media_type="application/x-ndjson")


async def _speak_say_fallback(text: str) -> Response:
    run_id = uuid.uuid4().hex
    tmp_aiff = f"/tmp/speech_{run_id}.aiff"
    tmp_mp3 = f"/tmp/speech_{run_id}.mp3"
    try:
        result = subprocess.run(
            ["say", "-v", "Samantha", "-o", tmp_aiff, "--", text],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0 or not os.path.exists(tmp_aiff):
            return Response(status_code=503, content=b"TTS unavailable")
        try:
            conv = subprocess.run(
                ["ffmpeg", "-y", "-i", tmp_aiff, "-acodec", "libmp3lame", "-q:a", "4", tmp_mp3],
                capture_output=True, timeout=15,
            )
            if conv.returncode == 0 and os.path.exists(tmp_mp3):
                return Response(content=Path(tmp_mp3).read_bytes(), media_type="audio/mpeg")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return Response(content=Path(tmp_aiff).read_bytes(), media_type="audio/aiff")
    except subprocess.TimeoutExpired:
        return Response(status_code=504, content=b"TTS timeout")
    except Exception as exc:
        return Response(status_code=500, content=str(exc).encode())
    finally:
        for path in (tmp_aiff, tmp_mp3):
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass


def _clean_for_tts(text: str) -> str:
    """Strip markdown and code so the TTS reads naturally."""
    text = re.sub(r"```[\s\S]*?```", ", code block, ", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\[INTERNAL[^\]]*\]", "", text)
    text = re.sub(r"\[SYSTEM[^\]]*\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    # Pass the app object directly (not the "app:app" import string) so this
    # works both as `python app.py` and inside a frozen PyInstaller binary.
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)
