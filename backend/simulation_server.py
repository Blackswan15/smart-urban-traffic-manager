import traci
import os
import sys
import threading
import asyncio
import queue
import json
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# --- 🗺️ CONFIGURATION: Mappings for your 'f1.net.xml' file ---

# Map SUMO edge IDs to cardinal directions based on your network file.
EDGE_TO_DIRECTION_MAP = {
    "E3": "North",  # Edge for traffic coming FROM the North
    "-E2": "South", # Edge for traffic coming FROM the South
    "-E0": "East",  # Edge for traffic coming FROM the East
    "E0": "West"   # Edge for traffic coming FROM the West
}

# Map the traffic light phase INDEX to a clear description.
PHASE_MAPS = {
    "clusterJ10_J14_J15_J16": {
        0: "East-West Green",
        2: "North-South Green",
    }
}
# --- END OF CONFIGURATION ---


# --- Your Original SimulationManager Class ---
MIN_GREEN_TIME = 10
YELLOW_PHASE_DURATION = 4

class SimulationManager:
    def __init__(self, sumo_cfg, use_gui=True, max_steps=5000):
        self.sumo_cfg = sumo_cfg
        self.use_gui = use_gui
        self.max_steps = max_steps
        self.traffic_lights = {}

    def run(self, data_queue: queue.Queue):
        """Starts SUMO, runs the simulation, and puts translated data into the queue."""
        sumo_binary = self._get_sumo_binary()
        if not sumo_binary:
            return
        
        traci.start([sumo_binary, "-c", self.sumo_cfg])
        self._discover_network_and_phases()
        all_edge_ids = traci.edge.getIDList()

        step = 0
        try:
            while step < self.max_steps and traci.simulation.getMinExpectedNumber() > 0:
                traci.simulationStep()
                
                # --- GATHER AND TRANSLATE DATA ---
                # 1. Get the raw data from Traci
                raw_vehicle_counts = {edge_id: traci.edge.getLastStepVehicleNumber(edge_id) 
                                      for edge_id in all_edge_ids}

                # 2. Create a new, user-friendly data structure
                human_readable_data = {
                    "step": step,
                    "waiting_vehicles": {},
                    "green_direction": "Unknown",
                    "raw_data": {} # Keep raw data for the JSON view
                }

                # 3. Translate vehicle counts using the EDGE_TO_DIRECTION_MAP
                for edge_id, direction in EDGE_TO_DIRECTION_MAP.items():
                    human_readable_data["waiting_vehicles"][direction] = raw_vehicle_counts.get(edge_id, 0)

                # 4. Translate traffic light states
                for tls_id, phase_map in PHASE_MAPS.items():
                    if tls_id in self.traffic_lights:
                        current_phase = traci.trafficlight.getPhase(tls_id)
                        phase_description = phase_map.get(current_phase, f"Yellow/Transition (Phase {current_phase})")
                        human_readable_data["green_direction"] = phase_description
                
                # 5. (Optional) Add raw data for the technical view on the frontend
                human_readable_data['raw_data'] = {
                    'vehicle_counts_per_edge': raw_vehicle_counts,
                    'traffic_light_id': list(PHASE_MAPS.keys())[0],
                    'current_phase_index': traci.trafficlight.getPhase(list(PHASE_MAPS.keys())[0])
                }

                # --- PUT THE NEW, SIMPLIFIED DATA IN QUEUE ---
                data_queue.put(human_readable_data)
                
                # --- Control Logic ---
                for tls_id in self.traffic_lights:
                    self._control_traffic_light_state_machine(tls_id, step, traci.trafficlight.getPhase(tls_id))
                    
                step += 1
        finally:
            traci.close()
            print("Simulation finished and Traci closed.")
            data_queue.put(None)

    def _discover_network_and_phases(self):
        all_tls_ids = traci.trafficlight.getIDList()
        for tls_id in all_tls_ids:
            logic = traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)[0]
            phase_to_lanes_map = {}
            green_phases = []
            for i, phase in enumerate(logic.phases):
                state = phase.state.lower()
                if 'g' in state and 'y' not in state:
                    green_phases.append(i)
                    phase_to_lanes_map[i] = set()
            yellow_phase_map = {}
            for green_idx in green_phases:
                next_phase_idx = (green_idx + 1) % len(logic.phases)
                if 'y' in logic.phases[next_phase_idx].state.lower():
                    yellow_phase_map[green_idx] = next_phase_idx
            controlled_links = traci.trafficlight.getControlledLinks(tls_id)
            for link_idx, links in enumerate(controlled_links):
                for phase_idx in green_phases:
                    phase_state = logic.phases[phase_idx].state.lower()
                    if link_idx < len(phase_state) and phase_state[link_idx] == 'g':
                        for link in links:
                            phase_to_lanes_map[phase_idx].add(link[0])
            self.traffic_lights[tls_id] = {
                'phase_to_lanes': {p: list(l) for p, l in phase_to_lanes_map.items() if l},
                'yellow_phase_map': yellow_phase_map,
                'timer': 0,
                'state': 'GREEN',
                'target_phase': None
            }
        print("Discovered and mapped traffic light phases.")

    def _control_traffic_light_state_machine(self, tls_id, step, current_phase_index):
        tls_data = self.traffic_lights[tls_id]
        tls_data['timer'] += 1
        if tls_data['state'] == 'YELLOW':
            if tls_data['timer'] >= YELLOW_PHASE_DURATION:
                traci.trafficlight.setPhase(tls_id, tls_data['target_phase'])
                tls_data['state'] = 'GREEN'
                tls_data['timer'] = 0
            return
        if tls_data['state'] == 'GREEN':
            if tls_data['timer'] < MIN_GREEN_TIME:
                return
            max_pressure = -1
            best_phase_index = current_phase_index
            for phase_idx, lanes in tls_data['phase_to_lanes'].items():
                pressure = sum(traci.lane.getWaitingTime(lane) for lane in lanes)
                if pressure > max_pressure:
                    max_pressure = pressure
                    best_phase_index = phase_idx
            if best_phase_index != current_phase_index and max_pressure > 0:
                if current_phase_index in tls_data['yellow_phase_map']:
                    yellow_phase = tls_data['yellow_phase_map'][current_phase_index]
                    traci.trafficlight.setPhase(tls_id, yellow_phase)
                    tls_data['state'] = 'YELLOW'
                    tls_data['target_phase'] = best_phase_index
                    tls_data['timer'] = 0
                else:
                    traci.trafficlight.setPhase(tls_id, best_phase_index)
                    tls_data['timer'] = 0

    def _get_sumo_binary(self):
        if 'SUMO_HOME' in os.environ:
            sumo_home = os.environ['SUMO_HOME']
            binary = "sumo-gui" if self.use_gui else "sumo"
            return os.path.join(sumo_home, "bin", binary)
        else:
            sys.exit("please declare environment variable 'SUMO_HOME'")

# --- FastAPI and WebSocket Setup ---
app = FastAPI()
data_queue = queue.Queue()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

def run_simulation():
    """Function to be run in a separate thread."""
    sim_manager = SimulationManager("f1.sumocfg")
    sim_manager.run(data_queue)

async def broadcast_data():
    """Continuously checks the queue for new data and broadcasts it."""
    while True:
        try:
            data = data_queue.get_nowait()
            if data is None:
                await manager.broadcast(json.dumps({"status": "finished"}))
                break
            await manager.broadcast(json.dumps(data))
        except queue.Empty:
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error during broadcast: {e}")
            break

@app.on_event("startup")
async def startup_event():
    print("Starting simulation in a new thread...")
    sim_thread = threading.Thread(target=run_simulation, daemon=True)
    sim_thread.start()
    
    print("Starting data broadcaster...")
    asyncio.create_task(broadcast_data())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Client disconnected")

@app.get("/")
async def get():
    with open("index.html", "r") as f:
        return HTMLResponse(f.read())