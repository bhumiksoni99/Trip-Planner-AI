from tools.tavily_tool import search_tavily
from tools.flight_tool import search_flights
from backend import run_travel_agent

print(search_tavily("Find the best hotels in costwolds, England"))
# print(search_flights("Plan a trip from India to Londin"))

# user_input = input("Where is your next calling?")
# print(run_travel_agent(user_input)["final_response"])

