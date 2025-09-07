import traci
import os
import sys

# --- Constants for the State-Machine Algorithm ---
MIN_GREEN_TIME = 10        # Minimum time a phase must remain green
YELLOW_PHASE_DURATION = 4  # How long a yellow light should last

class SimulationManager:
    def __init__(self, sumo_cfg, use_gui=True, max_steps=5000):
        self.sumo_cfg = sumo_cfg
        self.use_gui = use_gui
        self.max_steps = max_steps
        self.traffic_lights = {}

    def run(self):
        """Starts SUMO and runs the main simulation loop with explicit yellow light control."""
        sumo_binary = self._get_sumo_binary()
        if not sumo_binary:
            return
        
        traci.start([sumo_binary, "-c", self.sumo_cfg])
        self._discover_network_and_phases()

        step = 0
        while step < self.max_steps and traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            for tls_id in self.traffic_lights:
                self._control_traffic_light_state_machine(tls_id, step)
            step += 1
        
        traci.close()
        print("Simulation finished.")

    def _discover_network_and_phases(self):
        """
        Discovers traffic lights, maps green phases to lanes, and identifies
        the corresponding yellow phase for each green phase.
        """
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

            # Find the yellow phase that follows each green phase
            yellow_phase_map = {}
            for green_idx in green_phases:
                # The yellow phase is typically the next one in the sequence
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
                'state': 'GREEN', # Can be 'GREEN' or 'YELLOW'
                'current_phase_index': traci.trafficlight.getPhase(tls_id),
                'target_phase': None
            }
        print("Discovered and mapped traffic light phases including yellow transitions.")

    def _control_traffic_light_state_machine(self, tls_id, step):
        """
        Controls a traffic light using a state machine ('GREEN' -> 'YELLOW' -> 'GREEN').
        """
        tls_data = self.traffic_lights[tls_id]
        tls_data['timer'] += 1

        # --- YELLOW STATE ---
        if tls_data['state'] == 'YELLOW':
            if tls_data['timer'] >= YELLOW_PHASE_DURATION:
                # Yellow time is over, switch to the target green phase
                traci.trafficlight.setPhase(tls_id, tls_data['target_phase'])
                tls_data['current_phase_index'] = tls_data['target_phase']
                tls_data['state'] = 'GREEN'
                tls_data['timer'] = 0
                print(f"Step {step}: TLS '{tls_id}' transitioning from YELLOW to GREEN phase {tls_data['current_phase_index']}.")
            return # Do nothing else while yellow

        # --- GREEN STATE ---
        if tls_data['state'] == 'GREEN':
            # Only check for a switch if the minimum green time has passed
            if tls_data['timer'] < MIN_GREEN_TIME:
                return

            max_pressure = -1
            best_phase_index = tls_data['current_phase_index']
            
            for phase_idx, lanes in tls_data['phase_to_lanes'].items():
                pressure = sum(traci.lane.getWaitingTime(lane) for lane in lanes)
                if pressure > max_pressure:
                    max_pressure = pressure
                    best_phase_index = phase_idx

            # If a better phase is found, start the transition to yellow
            if best_phase_index != tls_data['current_phase_index'] and max_pressure > 0:
                current_green_phase = tls_data['current_phase_index']
                if current_green_phase in tls_data['yellow_phase_map']:
                    yellow_phase = tls_data['yellow_phase_map'][current_green_phase]
                    traci.trafficlight.setPhase(tls_id, yellow_phase)
                    
                    tls_data['state'] = 'YELLOW'
                    tls_data['target_phase'] = best_phase_index
                    tls_data['timer'] = 0
                    print(f"Step {step}: TLS '{tls_id}' starting YELLOW transition from phase {current_green_phase} towards {best_phase_index}.")
                else:
                    # Fallback if no yellow phase is found (should not happen in a well-defined network)
                    traci.trafficlight.setPhase(tls_id, best_phase_index)
                    tls_data['current_phase_index'] = best_phase_index
                    tls_data['timer'] = 0

    def _get_sumo_binary(self):
        """Returns the path to the SUMO executable."""
        if 'SUMO_HOME' in os.environ:
            sumo_home = os.environ['SUMO_HOME']
            binary = "sumo-gui" if self.use_gui else "sumo"
            return os.path.join(sumo_home, "bin", binary)
        else:
            print("Please declare the environment variable 'SUMO_HOME'.", file=sys.stderr)
            return None

