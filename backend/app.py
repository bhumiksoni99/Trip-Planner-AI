from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import json
import queue
import threading
import uvicorn
import traceback
from agent import (
    run_travel_agent,
    resume_travel_agent,
    stream_travel_agent,
    stream_resume_travel_agent,
)
from place_preview import search_place

app = FastAPI(title="Travel Agent",description="Langgraph FastAPI app", version="1.0.0")

load_dotenv()

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
async def get_itinerary(request: TravelRequest):
    try:
        user_message = request.message.strip()

        if not user_message:
            return JSONResponse(status_code=400,content={
                "success": False,
                "error": "Messsage cannot be empty"
            })

        answer = run_travel_agent(user_message,request.thread_id)

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
async def resume_itinerary(request: ResumeRequest):
    """Answer the question a paused run is waiting on, and carry on planning."""
    try:
        answer = resume_travel_agent(request.thread_id, resume_value_of(request))

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
async def stream_itinerary(request: TravelRequest):
    """Plan a trip, reporting each agent as it starts and finishes; ends with the plan or a pause."""
    user_message = request.message.strip()

    if not user_message:
        return JSONResponse(status_code=400,content={
            "success": False,
            "error": "Message cannot be empty"
        })

    return StreamingResponse(
        sse(stream_travel_agent(user_message, request.thread_id)),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post('/api/travel/resume/stream')
async def stream_resume_itinerary(request: ResumeRequest):
    """Answer what a paused run is waiting on, reporting progress for the agents that run next."""
    return StreamingResponse(
        sse(stream_resume_travel_agent(request.thread_id, resume_value_of(request))),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


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
