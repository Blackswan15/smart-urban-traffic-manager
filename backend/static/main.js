
document.addEventListener('DOMContentLoaded', async () => {
    // --- Get references to ALL elements 
    const elements = {
        status: document.getElementById("status"),
        statusBar: document.getElementById("status-bar"),
        step: document.getElementById("step"),
        greenLight: document.getElementById("green-light"),
        vehicleCounts: document.getElementById("vehicle-counts"),
        controlMode: document.getElementById("control-mode"),
        toggleModeBtn: document.getElementById("toggle-mode-btn"),
        manualButtons: document.getElementById("manual-buttons"),
        forceNsBtn: document.getElementById("force-ns-btn"),
        forceEwBtn: document.getElementById("force-ew-btn"),
        canvas: document.getElementById("simulation-canvas")
    };

    //  Fetch network data and initialize renderer 
    const response = await fetch('/network_data');
    const networkData = await response.json();
    const renderer = RENDERER.init(elements.canvas, networkData);
    
    //  WebSocket Setup 
    const socket = new WebSocket(`ws://${window.location.host}/ws`);

    function sendCommand(command, value) {
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ command, value }));
        }
    }

    //  Event Listeners
    elements.toggleModeBtn.addEventListener("click", () => sendCommand("set_mode", elements.controlMode.textContent === "AUTO" ? "MANUAL" : "AUTO"));
    elements.forceNsBtn.addEventListener("click", () => sendCommand("force_phase", 2));
    elements.forceEwBtn.addEventListener("click", () => sendCommand("force_phase", 0));

    //  WebSocket Handlers
    socket.onopen = () => {
        elements.status.textContent = "Connected";
        elements.statusBar.className = "status-connected";
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.status === "finished") {
            elements.status.textContent = "Simulation Finished";
            return;
        }

        // Update text elements
        elements.step.textContent = data.step;
        elements.greenLight.textContent = data.green_direction;
        elements.controlMode.textContent = data.control_mode.toUpperCase();
        elements.toggleModeBtn.textContent = data.control_mode === "manual" ? "Switch to AUTO Mode" : "Switch to MANUAL Mode";
        elements.manualButtons.style.display = data.control_mode === "manual" ? "flex" : "none";

        elements.vehicleCounts.innerHTML = "";
        Object.entries(data.waiting_vehicles).forEach(([direction, count]) => {
            const p = document.createElement("p");
            p.innerHTML = `<strong>${direction}:</strong> ${count} vehicles`;
            elements.vehicleCounts.appendChild(p);
        });

        // Update visualization
        renderer.drawScene(data);
    };

    socket.onclose = () => {
        elements.status.textContent = "Disconnected";
        elements.statusBar.className = "status-disconnected";
    };

    socket.onerror = () => {
        elements.status.textContent = "Connection Error!";
        elements.statusBar.className = "status-disconnected";
    };
});