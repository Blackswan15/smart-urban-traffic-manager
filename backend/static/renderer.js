// RENDERER LOGIC
const RENDERER = {
    init(canvas, networkData) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.networkData = networkData;
        this.resize();
        window.addEventListener('resize', () => this.resize());
        return this;
    },
    resize() {
        const dpr = window.devicePixelRatio || 1;
        const rect = this.canvas.getBoundingClientRect();
        this.canvas.width = rect.width * dpr;
        this.canvas.height = rect.height * dpr;
        this.ctx.scale(dpr, dpr);
        this.transform = this.calculateTransform();
    },
    calculateTransform() {
        const bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
        this.networkData.edges.forEach(edge => {
            edge.shape.forEach(p => {
                bounds.minX = Math.min(bounds.minX, p.x);
                bounds.maxX = Math.max(bounds.maxX, p.x);
                bounds.minY = Math.min(bounds.minY, p.y);
                bounds.maxY = Math.max(bounds.maxY, p.y);
            });
        });
        const padding = 20;
        const netWidth = bounds.maxX - bounds.minX;
        const netHeight = bounds.maxY - bounds.minY;
        const scaleX = (this.canvas.clientWidth - padding * 2) / netWidth;
        const scaleY = (this.canvas.clientHeight - padding * 2) / netHeight;
        const scale = Math.min(scaleX, scaleY);
        const offsetX = (this.canvas.clientWidth / 2) - (scale * (bounds.minX + netWidth / 2));
        const offsetY = this.canvas.clientHeight - ((this.canvas.clientHeight / 2) - (scale * (bounds.minY + netHeight / 2)));
        
        return { scale, offsetX, offsetY };
    },
    _transform(p) {
        return {
            x: p.x * this.transform.scale + this.transform.offsetX,
            y: this.canvas.clientHeight - (p.y * this.transform.scale + (this.canvas.clientHeight - this.transform.offsetY))
        };
    },
    drawScene(data) {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.drawIntersection();
        this.drawTrafficLights(data.tlsState);
        if (data.vehicles) data.vehicles.forEach(v => this.drawVehicle(v));
    },
    drawIntersection() {
        this.networkData.edges.forEach(edge => {
            if (edge.shape.length < 2) return;
            // Road Surface
            this.ctx.beginPath();
            const startPoint = this._transform(edge.shape[0]);
            this.ctx.moveTo(startPoint.x, startPoint.y);
            for (let i = 1; i < edge.shape.length; i++) {
                this.ctx.lineTo(this._transform(edge.shape[i]).x, this._transform(edge.shape[i]).y);
            }
            this.ctx.lineWidth = edge.width * edge.lanes * this.transform.scale;
            this.ctx.strokeStyle = '#2d3436';
            this.ctx.lineCap = 'round';
            this.ctx.stroke();

            // Lane Markings
            if (edge.lanes > 1) {
                this.ctx.beginPath();
                this.ctx.moveTo(startPoint.x, startPoint.y);
                for (let i = 1; i < edge.shape.length; i++) {
                     this.ctx.lineTo(this._transform(edge.shape[i]).x, this._transform(edge.shape[i]).y);
                }
                this.ctx.lineWidth = 1;
                this.ctx.strokeStyle = '#555';
                this.ctx.setLineDash([5, 10]);
                this.ctx.stroke();
                this.ctx.setLineDash([]);
            }
        });
    },
    drawVehicle(vehicle) {
        const { x, y, angle, speed, id } = vehicle;
        const pos = this._transform({ x, y });
        const vLength = 4.5 * this.transform.scale;
        const vWidth = 2.0 * this.transform.scale;
        
        this.ctx.save();
        this.ctx.translate(pos.x, pos.y);
        this.ctx.rotate(-(angle - 90) * Math.PI / 180);
        
        this.ctx.fillStyle = speed < 0.2 ? "#ff4757" : "#f0c43c"; // Red when stopped
        this.ctx.fillRect(-vLength / 2, -vWidth / 2, vLength, vWidth);
        
        this.ctx.fillStyle = "#55b6f2"; // Windshield
        this.ctx.fillRect(vLength / 4, -vWidth / 2, vLength / 4, vWidth);
        
        this.ctx.rotate(90 * Math.PI / 180);
        this.ctx.fillStyle = "black";
        this.ctx.font = `bold ${Math.max(7, vWidth * 0.7)}px Poppins`;
        this.ctx.textAlign = "center";
        this.ctx.textBaseline = "middle";
        this.ctx.fillText(id.split('.')[0], 0, 0);

        this.ctx.restore();
    },
    drawTrafficLights(tlsState) {
        if (!tlsState || !this.networkData.tls) return;
        const tlsId = Object.keys(this.networkData.tls)[0];
        if (!tlsId || !tlsState[tlsId]) return;

        const stateString = tlsState[tlsId].state;
        const links = this.networkData.tls[tlsId].links;
        
        links.forEach((link) => {
            const index = link.linkIndex;
            if (index >= stateString.length) return;
            const stateChar = stateString[index].toLowerCase();
            const color = {'r': '#ff4757', 'y': '#f0c43c', 'g': '#2ed573'}[stateChar];

            if (color) {
                const viaLane = this.networkData.lanes.find(l => l.id === link.via);
                if (!viaLane || viaLane.shape.length < 2) return;
                
                const lightPos = this._transform(viaLane.shape[0]);
                this.ctx.beginPath();
                this.ctx.arc(lightPos.x, lightPos.y, 2.5, 0, 2 * Math.PI);
                this.ctx.fillStyle = color;
                this.ctx.fill();
            }
        });
    }
};