from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from simulation_manager import SimulationManager # Import the manager
import threading

app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for simplicity
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "Backend is running!"}

@app.post("/run-simulation")
def run_simulation_endpoint():
    """
    API endpoint to start the SUMO simulation in a background thread.
    """
    try:
        # Configure and create the simulation manager
        # Ensure this path is correct relative to where you run uvicorn
        sumo_config_file = "../sumo_files/f1.sumocfg"
        sim_manager = SimulationManager(sumo_config_file, use_gui=True)
        
        # Run the simulation in a separate thread so the API doesn't block
        simulation_thread = threading.Thread(target=sim_manager.run)
        simulation_thread.start()
        
        return {"message": "Simulation started successfully in the background."}
    except Exception as e:
        return {"error": f"Failed to start simulation: {e}"}