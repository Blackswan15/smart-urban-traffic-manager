import traci
import os

class SimulationManager:
    def __init__(self, sumo_cfg, use_gui=True, max_steps=5000):
        self.sumo_cfg = sumo_cfg
        self.use_gui = use_gui
        self.max_steps = max_steps
        self.traffic_lights = {}
        self.lane_to_detector_map = {}

    def run(self):
        """Starts SUMO and runs the main simulation loop."""
        sumo_binary = self._get_sumo_binary()
        traci.start([sumo_binary, "-c", self.sumo_cfg])

        step = 0
        while step < self.max_steps and traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            
            if step == 0:
                self._discover_network()

            for tls_id in self.traffic_lights:
                self._control_traffic_light_threshold(tls_id, step)

            step += 1
        
        traci.close()
        print("Simulation finished.")

    def _discover_network(self):
        """Discovers network components and initializes timers and states."""
        all_tls_ids = traci.trafficlight.getIDList()
        for tls_id in all_tls_ids:
            # We need to understand the phases to control the light
            logic = traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)[0]
            phases = logic.phases
            
            self.traffic_lights[tls_id] = {
                'lanes': traci.trafficlight.getControlledLanes(tls_id),
                'green_phase_timer': 0,
                'is_green': False,
                'phases': phases # Store the phase definitions
            }
        print(f"Discovered traffic lights: {list(self.traffic_lights.keys())}")

        all_detector_ids = traci.lanearea.getIDList()
        for det_id in all_detector_ids:
            lane_id = traci.lanearea.getLaneID(det_id)
            self.lane_to_detector_map[lane_id] = det_id
        print(f"Discovered {len(all_detector_ids)} detectors.")
    
    def _control_traffic_light_threshold(self, tls_id, step):
        """Controls a traffic light based on a vehicle count threshold."""
        VEHICLE_THRESHOLD = 20
        GREEN_TIME_DURATION = 20  # Give 20 seconds of green time

        # If the light is currently green, let the timer run down
        if self.traffic_lights[tls_id]['is_green']:
            self.traffic_lights[tls_id]['green_phase_timer'] -= 1
            if self.traffic_lights[tls_id]['green_phase_timer'] <= 0:
                self.traffic_lights[tls_id]['is_green'] = False
                # Switch to an all-red or yellow phase before the next green
                # This logic assumes a simple phase cycle (green -> yellow -> green)
                current_phase = traci.trafficlight.getPhase(tls_id)
                traci.trafficlight.setPhase(tls_id, current_phase + 1)
            return

        # Check all incoming lanes for queues
        for i, phase in enumerate(self.traffic_lights[tls_id]['phases']):
            # Only check green phases ('G' or 'g' in the state string)
            if 'g' not in phase.state.lower():
                continue

            # Check the first lane associated with this green phase
            # Note: This is a simplification. A real system would check all lanes in the phase.
            controlled_lanes = traci.trafficlight.getControlledLanes(tls_id)
            # Find a lane that is green in this phase to check its queue
            target_lane = None
            for link_index in traci.trafficlight.getControlledLinks(tls_id)[i]:
                # getControlledLinks returns tuples of (incomingLane, outgoingLane, viaLane)
                target_lane = link_index[0] 
                break # Just check the first lane for simplicity
            
            if target_lane and target_lane in self.lane_to_detector_map:
                detector_id = self.lane_to_detector_map[target_lane]
                car_count = traci.lanearea.getLastStepHaltingNumber(detector_id)

                if car_count > VEHICLE_THRESHOLD:
                    # Threshold exceeded, trigger this green phase
                    traci.trafficlight.setPhase(tls_id, i)
                    self.traffic_lights[tls_id]['is_green'] = True
                    self.traffic_lights[tls_id]['green_phase_timer'] = GREEN_TIME_DURATION
                    print(f"Step {step}: Threshold exceeded on a lane for TLS '{tls_id}'. Activating phase {i} for {GREEN_TIME_DURATION}s.")
                    break # Stop checking other phases for this step

    def _get_sumo_binary(self):
        """Returns the path to the SUMO executable."""
        sumo_home = os.environ.get("SUMO_HOME", ".")
        return os.path.join(sumo_home, "bin", "sumo-gui" if self.use_gui else "sumo")