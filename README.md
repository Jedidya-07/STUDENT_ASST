# Student Assist

A student productivity assistant for capturing tasks by text or voice, organising deadlines, and tracking academic and personal schedules.

## Current MVP

- React + Vite dashboard
- FastAPI backend with SQLite persistence
- Task creation, completion, deletion and upcoming views
- Assistant text input with a mock parser
- Browser speech-to-text (Chrome / Edge)
- Subtask suggestions for exams and assignments
- Configurable remote LLM endpoint through the backend

## Run locally

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 2. Frontend

In a second terminal, from the repository root:

```bash
npm install
npm run dev
```

Open http://localhost:5173

## Connect the LLM later

Copy `backend/.env.example` to `backend/.env` and set:

```env
LLM_API_URL=http://YOUR-OTHER-LAPTOP-IP:PORT/your-parse-route
LLM_API_KEY=
CORS_ORIGINS=http://localhost:5173
```

The remote endpoint currently receives JSON `{"text":"..."}` and should return:

```json
{
  "reply": "I organised your schedule.",
  "tasks": [
    {
      "title": "DBMS exam",
      "category": "Exam",
      "date": "2026-11-20",
      "time": "10:00",
      "priority": "High",
      "description": "",
      "subtasks": ["Revise Unit 1", "Practice questions"]
    }
  ]
}
```

For another laptop on the same Wi-Fi, use its LAN IP (for example `http://192.168.1.20:8001/parse`) and ensure its firewall allows the port. The LLM service should bind to `0.0.0.0`.

## Notes

- The current parser is deliberately a placeholder, not a real language model. It provides a simple local fallback for testing.
- Browser speech recognition requires a supported browser and microphone permission.
- Browser notifications and scheduled background reminders are not yet implemented; task dates and times are currently stored and shown in the app.
