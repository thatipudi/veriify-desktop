# Mock Interview Coach

AI-powered, fully local interview preparation tool. Simulates real job interviews end-to-end using Ollama (llama3.1:8b). No cloud APIs. No data leaves your machine.

## Setup

### 1. Install Ollama

```bash
brew install ollama
```

### 2. Pull the model

```bash
ollama pull llama3.1:8b
```

### 3. Start Ollama

```bash
ollama serve
```

Keep this running in a terminal tab.

### 4. Install Python dependencies

```bash
cd interview-coach
pip install -r requirements.txt
```

> If pytesseract fails, install Tesseract: `brew install tesseract`

### 5. Run the app

```bash
python app.py
```

### 6. Open in browser

```
http://localhost:8000
```

---

## Usage

1. **Setup screen** — Enter your name, paste or upload the Job Description, upload your Resume (PDF or DOCX).
2. **Analyze** — The AI reads both documents, detects the role, industry, seniority, and interview round. You can override the round type.
3. **Start Interview** — A realistic interviewer persona greets you and runs a full 10-question interview session.
4. **Answer naturally** — Type your answers. The interviewer responds, follows up, probes, and guides the conversation like a real human.
5. **Feedback Report** — After the interview, get a scored, honest, per-answer breakdown with ideal answers and study recommendations.
6. **Download PDF** — Export the full report using your browser's print-to-PDF.

## Supported Formats

| Input | Formats |
|-------|---------|
| Resume | PDF, DOCX |
| Job Description | Paste text, PDF, PNG/JPG screenshot |

## Interview Rounds

| Round | Focus |
|-------|-------|
| Screening | Motivation, culture fit, background, salary |
| Technical | Role-specific skills, system design, coding concepts |
| Behavioral | STAR-format stories, leadership, conflict, failure |
| HR | Compensation, benefits, start date, policies |
| Final | Executive presence, vision, strategic thinking |

## Hardware Requirements

- Apple M-series Mac (M1/M2/M3/M4) with 8GB+ RAM
- 16GB RAM recommended for llama3.1:8b
- ~5GB disk space for the model
