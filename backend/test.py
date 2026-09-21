from agent import run_travel_agent, resume_travel_agent

result = run_travel_agent("Plan a trip to London")

# With REQUIRE_APPROVAL=true the run pauses at hil_agent, so approve it to get the plan
if result["awaiting_approval"]:
    print("Paused for approval:", result["approval_request"]["question"])
    result = resume_travel_agent(result["thread_id"], approved=True)

print(result["final_response"])
