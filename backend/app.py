from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import traceback
from backend import run_travel_agent

app = FastAPI(title="Travel Agent",description="Langgraph FastAPI app", version="1.0.0")

load_dotenv()

class TravelRequest(BaseModel):
    message:str
    thread_id: str | None = None

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


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
