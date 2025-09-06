import traci
import os

# --- Configuration ---
# This script will work with any SUMO config file.
SUMO_CONFIG_FILE = "../sumo_files/newsumo.sumocfg"

# --- SUMO Connection ---
sumo_binary = os.path.join(os.environ.get("SUMO_HOME", "."), "bin", "sumo-gui")
traci.start([sumo_binary, "-c", SUMO_CONFIG_FILE])

# Dictionary to hold information about each traffic light we find
traffic_lights = {}

# --- Main Simulation Loop ---
step = 0
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    # --- Discovery Step (runs only once at the beginning) ---
    if step == 0:
        # 1. Get all traffic light IDs from the simulation
        all_tls_ids = traci.trafficlight.getIDList()
        print(f"Discovered traffic lights: {all_tls_ids}")

        # 2. For each traffic light, find its incoming lanes
        for tls_id in all_tls_ids:
            traffic_lights[tls_id] = {'lanes': set()}
            # Get all lanes controlled by this traffic light
            controlled_lanes = traci.trafficlight.getControlledLanes(tls_id)
            # Find incoming lanes (lanes that lead to the intersection)
            for lane in controlled_lanes:
                # This is a simple way to find incoming lanes
                if lane not in traffic_lights[tls_id]['lanes']:
                     traffic_lights[tls_id]['lanes'].add(lane)
        
        print(f"Discovered controlled lanes: {traffic_lights}")

    # --- Control Logic (runs on every step for every discovered light) ---
    for tls_id in traffic_lights:
        # Your generic control logic goes here.
        # It will be applied to every traffic light found in the network.
        
        # Example: Get the state for the current traffic light
        current_phase = traci.trafficlight.getPhase(tls_id)
        
        # You would then get queue lengths for the lanes associated with this tls_id
        # (e.g., from detectors you placed with a consistent naming convention)
        
        # Example: Simple logic to print the phase
        if step % 20 == 0:
            print(f"Traffic Light '{tls_id}' is in phase {current_phase}")

    step += 1

# --- Cleanup ---
traci.close()