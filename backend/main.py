from datetime import date, datetime, timedelta
from typing import Optional
import os, re
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, Session, create_engine, select\nfrom sqlalchemy import Column\nfrom sqlalchemy.types import JSON

load_dotenv()
DB_URL = "sqlite:///./student_assist.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    category: str = "Study"
    date: str
    time: str = "18:00"
    priority: str = "Medium"
    status: str = "pending"
    description: str = ""
    subtasks: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

class TaskInput(SQLModel):
    title: str
    category: str = "Study"
    date: str
    time: str = "18:00"
    priority: str = "Medium"
    status: str = "pending"
    description: str = ""
    subtasks: list[str] = []

class ParseInput(SQLModel):
    text: str

app = FastAPI(title="Student Assist API", version="1.0.0")
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins] + ["http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    SQLModel.metadata.create_all(engine)

@app.get("/")
def health():
    return {"app": "Student Assist API", "status": "online"}

@app.get("/health")
def health_check():
    return {"status": "ok", "llm_configured": bool(os.getenv("LLM_API_URL"))}

@app.get("/tasks")
def list_tasks():
    with Session(engine) as session:
        return session.exec(select(Task).order_by(Task.date, Task.time)).all()

@app.post("/tasks")
def create_task(payload: TaskInput):
    with Session(engine) as session:
        task = Task(**payload.model_dump())
        session.add(task); session.commit(); session.refresh(task)
        return task

@app.put("/tasks/{task_id}")
def update_task(task_id: int, payload: TaskInput):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task: raise HTTPException(404, "Task not found")
        for key, value in payload.model_dump().items(): setattr(task, key, value)
        session.add(task); session.commit(); session.refresh(task)
        return task

@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task: raise HTTPException(404, "Task not found")
        session.delete(task); session.commit()
        return {"deleted": True}

def mock_parse(text: str):
    lower = text.lower()
    target = date.today() + (timedelta(days=1) if "tomorrow" in lower else timedelta(days=0))
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lower)
    time_value = "18:00"
    if time_match:
        hour = int(time_match.group(1)); minute = int(time_match.group(2) or 0)
        if time_match.group(3) == "pm" and hour != 12: hour += 12
        if time_match.group(3) == "am" and hour == 12: hour = 0
        time_value = f"{hour:02d}:{minute:02d}"
    category = "Exam" if "exam" in lower or "test" in lower else "Assignment" if "assignment" in lower or "submit" in lower else "Personal" if "gym" in lower or "workout" in lower else "Study"
    title = text.strip().rstrip(".!?")
    subtasks = []
    if category == "Assignment": subtasks = ["Review requirements", "Complete the work", "Check and submit"]
    elif category == "Exam": subtasks = ["Review syllabus and notes", "Practice important questions", "Final revision"]
    task = {"title": title[:120], "category": category, "date": target.isoformat(), "time": time_value, "priority": "High" if category in ("Exam", "Assignment") else "Medium", "description": "Created from assistant text input.", "subtasks": subtasks}
    return {"tasks": [task], "reply": f"I captured this as a {category.lower()} task for {target.strftime('%A, %d %b')}. You can edit the details in your task list."}

@app.post("/assistant/parse")
async def parse_assistant(payload: ParseInput):
    text = payload.text.strip()
    if not text: raise HTTPException(400, "Text is required")
    endpoint = os.getenv("LLM_API_URL", "").strip()
    if endpoint:
        headers = {"Content-Type": "application/json"}
        if os.getenv("LLM_API_KEY"): headers["Authorization"] = f"Bearer {os.getenv('LLM_API_KEY')}"
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                response = await client.post(endpoint, json={"text": text}, headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            # Keep the student workflow usable if the remote model is temporarily offline.
            fallback = mock_parse(text)
            fallback["reply"] = "AI service unavailable; I saved a basic draft instead. " + fallback["reply"]
            return fallback
    return mock_parse(text)
