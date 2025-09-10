import asyncio
import json
import os
import queue
import sys
import threading
from typing import List, Dict, Any

import traci
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from network_parser import parse_network

# --- CONFIGURATION ---
SUMO_CONFIG_FILE = "f1.sumocfg"
NETWORK_FILE = "f1.net.xml"
EDGE_TO_DIRECTION_MAP = {"E3": "North", "-E2": "South", "-E0": "East", "E0": "West"}
PHASE_MAPS = {"clusterJ10_J14_J15_J16": {0: "East-West Green", 2: "North-South Green"}}
MIN_GREEN_TIME = 10
YELLOW_PHASE_DURATION = 4

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)
    def disconnect(self, ws: WebSocket):
        self.active_connections.remove(ws)
    async def broadcast(self, msg: str):
        for conn in self.active_connections:
            await conn.send_text(msg)

# --- SIMULATION MANAGER ---
class SimulationManager:
    def __init__(self, sumo_cfg, command_queue: queue.Queue, use_gui=True):
        self.sumo_cfg = sumo_cfg
        self.command_queue = command_queue
        self.use_gui = use_gui
        self.traffic_lights = {}
        self.control_mode = "auto"
        self.manual_phase_target = None
        self.manual_phase_changed = False

    def _process_commands(self):
        try:
            cmd = self.command_queue.get_nowait()
            command, value = cmd.get("command"), cmd.get("value")
            if command == "set_mode":
                self.control_mode = value.lower()
                self.manual_phase_target = None
                print(f"Control mode changed to: {self.control_mode}")
            elif command == "force_phase" and self.control_mode == "manual":
                if self.manual_phase_target != value:
                    self.manual_phase_target = value
                    self.manual_phase_changed = True
                    print(f"Manual override: Forcing phase {self.manual_phase_target}")
        except queue.Empty:
            pass

    def run(self, data_queue: queue.Queue):
        sumo_binary = self._get_sumo_binary()
        if not sumo_binary: return
        traci.start([sumo_binary, "-c", self.sumo_cfg])
        self._discover_network_and_phases()
        
        step = 0
        while traci.simulation.getMinExpectedNumber() > 0:
            self._process_commands()

            if self.control_mode == "manual" and self.manual_phase_changed:
                for tls_id in self.traffic_lights:
                    traci.trafficlight.setPhase(tls_id, self.manual_phase_target)
                self.manual_phase_changed = False
            
            traci.simulationStep()
            
            if self.control_mode == "auto":
                for tls_id in self.traffic_lights:
                    self._control_traffic_light_state_machine(tls_id, traci.trafficlight.getPhase(tls_id))

            data_queue.put(self._gather_data(step))
            step += 1
        
        traci.close()
        data_queue.put(None)

    def _gather_data(self, step: int) -> Dict[str, Any]:
        vehicles = [{
            "id": vid, "x": pos[0], "y": pos[1],
            "angle": traci.vehicle.getAngle(vid),
            "speed": traci.vehicle.getSpeed(vid)
        } for vid, pos in [(v, traci.vehicle.getPosition(v)) for v in traci.vehicle.getIDList()]]

        tls_states = {tls_id: {"state": traci.trafficlight.getRedYellowGreenState(tls_id)} for tls_id in self.traffic_lights}
        waiting_counts = {direction: traci.edge.getLastStepHaltingNumber(edge) for edge, direction in EDGE_TO_DIRECTION_MAP.items()}
        
        green_direction = "Unknown"
        for tls_id, phase_map in PHASE_MAPS.items():
            if tls_id in self.traffic_lights:
                current_phase = traci.trafficlight.getPhase(tls_id)
                green_direction = phase_map.get(current_phase, f"Yellow (Phase {current_phase})")

        return {
            "step": step, "waiting_vehicles": waiting_counts,
            "green_direction": green_direction, "control_mode": self.control_mode,
            "vehicles": vehicles, "tlsState": tls_states
        }

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
                'yellow_phase_map': yellow_phase_map, 'timer': 0,
                'state': 'GREEN', 'target_phase': None
            }
        print("Discovered and mapped traffic light phases.")

    def _control_traffic_light_state_machine(self, tls_id, current_phase_index):
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
            return os.path.join(os.environ['SUMO_HOME'], "bin", "sumo-gui" if self.use_gui else "sumo")
        sys.exit("Please declare environment variable 'SUMO_HOME'")

# --- FASTAPI APP ---
app = FastAPI()
data_queue, command_queue = queue.Queue(), queue.Queue()
app.mount("/static", StaticFiles(directory="static"), name="static")
network_data = parse_network(NETWORK_FILE)
manager = ConnectionManager()

@app.on_event("startup")
def startup_event():
    sim_manager = SimulationManager(SUMO_CONFIG_FILE, command_queue)
    threading.Thread(target=sim_manager.run, args=(data_queue,), daemon=True).start()
    asyncio.create_task(broadcast_data())

async def broadcast_data():
    while True:
        try:
            data = data_queue.get_nowait()
            if data is None: await manager.broadcast(json.dumps({"status": "finished"})); break
            await manager.broadcast(json.dumps(data))
        except queue.Empty: await asyncio.sleep(0.05)
        except Exception: break

@app.get("/")
async def get_root():
    return HTMLResponse(open("static/index.html", "r", encoding="utf-8").read())

@app.get("/network_data")
async def get_network_data():
    return JSONResponse(content=network_data)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: command_queue.put(json.loads(await websocket.receive_text()))
    except WebSocketDisconnect: manager.disconnect(websocket)