from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import json
import queue
import re
import threading
import time
import psycopg
import uvicorn
import traceback
from typing import Annotated
from uuid import uuid4
import chats
import db
import runs
from agent import (
    chat_messages,
    forget_thread,
    pending_pause,
    run_travel_agent,
    resume_travel_agent,
    stream_travel_agent,
    stream_resume_travel_agent,
    title_of,
)
from auth import create_token, current_user, hash_password, optional_user, verify_password
from place_preview import search_place


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # The users and chats tables; LangGraph's own checkpoint tables are created when agent is imported
    db.create_tables()
    yield


app = FastAPI(title="Travel Agent",description="Langgraph FastAPI app", version="1.0.0", lifespan=lifespan)

load_dotenv()

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# The browser makes these: 32 hex characters. Anything else never reached a chat, so it's rejected here
ThreadId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class ClaimRequest(BaseModel):
    thread_ids: list[ThreadId] = Field(max_length=200)


def check_readable(thread_id: str, user: dict | None):
    """Someone else's chat is a 404, not a 403: the answer shouldn't say whether it exists"""
    if not chats.readable_by(thread_id, user):
        raise HTTPException(404, "Chat not found")


class SignupRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    # No minimum length here, so a wrong password gets the same answer however long it is
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


def account(user: dict) -> dict:
    """What the frontend gets back after signing up or logging in"""
    return {"success": True, "data": {"token": create_token(user["id"]), "user": {"id": user["id"], "email": user["email"]}}}


@app.post('/api/auth/signup')
def signup(request: SignupRequest):
    """Plain def, so FastAPI runs the password hashing and the database write in a worker thread"""
    email = request.email.strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(400, "That doesn't look like an email address.")

    try:
        user = db.fetch(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id::text AS id, email",
            (email, hash_password(request.password)),
        )[0]
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "An account with this email already exists. Log in instead.")

    return account(user)


@app.post('/api/auth/login')
def login(request: LoginRequest):
    rows = db.fetch(
        "SELECT id::text AS id, email, password_hash FROM users WHERE email = %s",
        (request.email.strip().lower(),),
    )
    user = rows[0] if rows else None

    # One message for both cases, so the answer doesn't reveal which emails have accounts
    if not verify_password(request.password, user["password_hash"] if user else None):
        raise HTTPException(401, "Wrong email or password.")

    return account(user)


@app.get('/api/auth/me')
def me(user: dict = Depends(current_user)):
    return {"success": True, "data": user}

class TravelRequest(BaseModel):
    message:str
    thread_id: str | None = None

class ResumeRequest(BaseModel):
    """Answers whatever the run paused on: the intake questions, or the approval question."""
    thread_id: str
    approved: bool | None = None
    feedback: str = ""
    answers: dict[str, str] | None = None
    skipped: bool = False

@app.get('/health')
async def health_check():
    return JSONResponse(status_code=200,content={
        "success": True,
        "status": "ok"
    })

@app.post('/api/travel')
def get_itinerary(request: TravelRequest, user: dict | None = Depends(optional_user)):
    """Plan a trip and wait for the whole plan. The UI uses the streaming route; this one is for curl.

    Plain def, so the planning run happens in a worker thread rather than on the event loop."""
    user_message = request.message.strip()

    if not user_message:
        return JSONResponse(status_code=400,content={
            "success": False,
            "error": "Message cannot be empty"
        })

    thread_id = request.thread_id or uuid4().hex
    check_readable(thread_id, user)  # outside the catch below, so a 404 stays a 404

    if user:
        chats.remember(thread_id, user["id"], title_of(user_message))

    started = time.perf_counter()
    try:
        answer = run_travel_agent(user_message, thread_id)
        # No progress events on this route, so the agent list is unknown and the outcome is read
        # from the payload alone
        runs.from_result(thread_id, user["id"] if user else None, "message", answer, [],
                         int((time.perf_counter() - started) * 1000))

        return JSONResponse(status_code=200,content = {
            "success":True,
            "data":answer
        })

    except Exception:
        traceback.print_exc()
        return JSONResponse(status_code=500,content={
            "success": False,
            "error": "Something went wrong while planning your trip. Please try again."
        })


def resume_value_of(request: ResumeRequest):
    """What the paused run is waiting for: the intake answers, or the approval decision."""
    if request.approved is None:
        return {"skipped": True} if request.skipped else dict(request.answers or {})
    return {"approved": request.approved, "feedback": request.feedback}


@app.post('/api/travel/resume')
def resume_itinerary(request: ResumeRequest, user: dict | None = Depends(optional_user)):
    """Answer the question a paused run is waiting on, and carry on planning."""
    check_readable(request.thread_id, user)

    if user:
        chats.touch(request.thread_id, user["id"])

    started = time.perf_counter()
    try:
        answer = resume_travel_agent(request.thread_id, resume_value_of(request))
        runs.from_result(request.thread_id, user["id"] if user else None,
                         "skip" if request.skipped else "answer", answer, [],
                         int((time.perf_counter() - started) * 1000))

        return JSONResponse(status_code=200,content = {
            "success":True,
            "data":answer
        })

    except Exception:
        traceback.print_exc()
        return JSONResponse(status_code=500,content={
            "success": False,
            "error": "Something went wrong while finishing your trip plan. Please try again."
        })


# Sent while no agent has finished, so idle proxies don't drop a connection that is still working
KEEPALIVE_SECONDS = 15

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",  # stops nginx-style proxies buffering the events
}


def tracked(events, thread_id: str, user: dict | None, source: str):
    """Passes the progress events straight through, noting what the run did on their way past.

    Wrapping the generator rather than the route is what makes this honest: the work happens inside
    the stream, so this is the only place that sees a run end, including one that ends by failing."""
    started = time.perf_counter()
    agents: list[str] = []
    result = None

    try:
        for event in events:
            if event["event"] == "agent_started":
                agents.append(event["data"]["agent"])
            elif event["event"] == "done":
                result = event["data"]
            yield event
    finally:
        elapsed = int((time.perf_counter() - started) * 1000)
        if result is None:
            # The stream stopped before the plan was finished, which a failure does
            runs.record(thread_id, user["id"] if user else None, source, "failed",
                        agents, 0, elapsed, None)
        else:
            runs.from_result(thread_id, user["id"] if user else None, source, result, agents, elapsed)


def sse(events):
    """Run a progress generator in a worker thread and hand what it yields out as server-sent events.

    The thread is what makes the keep-alive possible: this loop wakes up every few seconds
    whether or not an agent has finished.
    """
    outbox = queue.Queue()

    def worker():
        try:
            for event in events:
                outbox.put(("event", event))
        except Exception:
            traceback.print_exc()
            outbox.put(("error", "Something went wrong while planning your trip. Please try again."))
        finally:
            outbox.put(("end", None))

    threading.Thread(target=worker, daemon=True).start()

    while True:
        try:
            kind, payload = outbox.get(timeout=KEEPALIVE_SECONDS)
        except queue.Empty:
            yield ": keep-alive\n\n"
            continue

        if kind == "end":
            return

        if kind == "error":
            yield f"event: error\ndata: {json.dumps({'error': payload})}\n\n"
            return

        yield f"event: {payload['event']}\ndata: {json.dumps(payload['data'])}\n\n"


@app.post('/api/travel/stream')
def stream_itinerary(request: TravelRequest, user: dict | None = Depends(optional_user)):
    """Plan a trip, reporting each agent as it starts and finishes; ends with the plan or a pause.

    Plain def, so the ownership check runs in a worker thread rather than on the event loop."""
    user_message = request.message.strip()

    if not user_message:
        return JSONResponse(status_code=400,content={
            "success": False,
            "error": "Message cannot be empty"
        })

    thread_id = request.thread_id or uuid4().hex
    check_readable(thread_id, user)

    # A logged-in traveller's chats are listed from this row. A guest's chat has none until they log in
    if user:
        chats.remember(thread_id, user["id"], title_of(user_message))

    return StreamingResponse(
        sse(tracked(stream_travel_agent(user_message, thread_id), thread_id, user, "message")),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post('/api/travel/resume/stream')
def stream_resume_itinerary(request: ResumeRequest, user: dict | None = Depends(optional_user)):
    """Answer what a paused run is waiting on, reporting progress for the agents that run next."""
    check_readable(request.thread_id, user)

    if user:
        chats.touch(request.thread_id, user["id"])

    # Skipping the questions and answering them are different decisions, so they count separately
    return StreamingResponse(
        sse(tracked(stream_resume_travel_agent(request.thread_id, resume_value_of(request)),
                    request.thread_id, user, "skip" if request.skipped else "answer")),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.get('/api/chats')
def list_chats(user: dict = Depends(current_user)):
    """The logged-in traveller's chats, newest first"""
    return {"success": True, "data": chats.list_for(user["id"])}


@app.get('/api/chats/{thread_id}')
def read_chat(thread_id: ThreadId, user: dict | None = Depends(optional_user)):
    """One chat, rebuilt from its checkpoint, with whatever question it's paused on"""
    check_readable(thread_id, user)
    messages = chat_messages(thread_id)

    if not messages:
        raise HTTPException(404, "Chat not found")

    # A guest's chat has no row to hold a title, so it comes from the first thing they asked for
    first_message = next((message["content"] for message in messages if message["role"] == "user"), "New trip")
    title = chats.title_of_chat(thread_id) or title_of(first_message)

    return {"success": True, "data": {"id": thread_id, "title": title, "messages": messages, "pause": pending_pause(thread_id)}}


@app.delete('/api/chats/{thread_id}')
def delete_chat(thread_id: ThreadId, user: dict = Depends(current_user)):
    """Deletes the chat and its checkpoints, so nothing is left behind"""
    if not chats.delete(thread_id, user["id"]):
        raise HTTPException(404, "Chat not found")

    forget_thread(thread_id)
    return {"success": True, "data": {"id": thread_id}}


@app.post('/api/chats/claim')
def claim_chats(request: ClaimRequest, user: dict = Depends(current_user)):
    """Hand the chats a traveller planned as a guest to the account they just logged into"""
    def title_for(thread_id: str) -> str:
        messages = chat_messages(thread_id)
        first_message = next((message["content"] for message in messages if message["role"] == "user"), "")
        return title_of(first_message) if first_message else "New trip"

    return {"success": True, "data": {"claimed": chats.claim(request.thread_ids, user["id"], title_for)}}


@app.get('/api/place')
def place_preview(q: str):
    """Photos and links for a place, shown in the app instead of sending the traveller to Google.

    Plain def, not async def, so FastAPI runs the search in a worker thread and one
    slow lookup can't block everything else the server is doing.
    """
    try:
        query = q.strip()
        if not query:
            return JSONResponse(status_code=400,content={
                "success": False,
                "error": "Query cannot be empty"
            })

        return JSONResponse(status_code=200,content = {
            "success":True,
            "data": search_place(query)
        })

    except Exception:
        traceback.print_exc()
        return JSONResponse(status_code=500,content={
            "success": False,
            "error": "Couldn't load a preview for this place."
        })


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
