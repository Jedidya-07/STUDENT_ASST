from datetime import date, datetime, timedelta
from typing import Optional
import os, re, json
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, Session, create_engine, select
from sqlalchemy import Column
from sqlalchemy.types import JSON

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
    base = os.getenv("LLM_API_URL", "").strip().rstrip("/")
    if not base: return mock_parse(text)
    endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + os.getenv("LLM_API_KEY", "lm-studio")}
    system_prompt = (
        "You are Student Assist. Extract EVERY distinct task/event and split unrelated activities. "
        "Create useful subtasks for exams and assignments. Do not invent deadlines; if missing use today and 18:00 as draft defaults. "
        "Return ONLY valid JSON: {\"reply\":\"confirmation\",\"tasks\":[{\"title\":\"...\",\"category\":\"Exam|Assignment|Study|Personal\",\"date\":\"YYYY-MM-DD\",\"time\":\"HH:MM\",\"priority\":\"High|Medium|Low\",\"description\":\"...\",\"subtasks\":[\"...\"]}]}. "
        f"Today is {date.today().isoformat()}. Interpret relative dates from today."
    )
    body = {"model": os.getenv("LLM_MODEL", "qwen/qwen3.5-9b"), "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": text}], "temperature": 0.2, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(endpoint, json=body, headers=headers)
            response.raise_for_status()
            result = response.json()
        content = result["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\\s*|\\s*```$", "", str(content).strip(), flags=re.IGNORECASE)
        data = json.loads(content)
        tasks = data.get("tasks", [])
        if not isinstance(tasks, list) or not tasks: raise ValueError("No tasks returned")
        for task in tasks:
            task.setdefault("date", date.today().isoformat()); task.setdefault("time", "18:00")
            task.setdefault("category", "Study"); task.setdefault("priority", "Medium")
            task.setdefault("description", ""); task.setdefault("subtasks", [])
        return {"reply": data.get("reply", "I organised your tasks."), "tasks": tasks}
    except Exception:
        fallback = mock_parse(text)
        fallback["reply"] = "LLM unavailable or returned invalid data; showing a basic draft. " + fallback["reply"]
        return fallback
