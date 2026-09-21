from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import traceback
from agent import run_travel_agent, resume_travel_agent
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


@app.post('/api/travel/resume')
async def resume_itinerary(request: ResumeRequest):
    """Answer the question a paused run is waiting on, and carry on planning."""
    try:
        if request.approved is None:
            resume_value = {"skipped": True} if request.skipped else dict(request.answers or {})
        else:
            resume_value = {"approved": request.approved, "feedback": request.feedback}

        answer = resume_travel_agent(request.thread_id, resume_value)

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
