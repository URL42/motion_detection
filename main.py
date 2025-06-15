import network
import socket
import uasyncio as asyncio
import machine
import time
import math
from secrets import SSID, PASSWORD
from rd03d import RD03D  # External radar library

try:
    import ujson as json
except ImportError:
    import json

# -------------------------
# Wi-Fi Setup
# -------------------------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)
while not wlan.isconnected():
    time.sleep(0.5)
print("Connected to WiFi, IP:", wlan.ifconfig()[0])

# -------------------------
# Initialize Radar
# -------------------------
radar = RD03D(uart_id=0, tx_pin=0, rx_pin=1, multi_mode=True)

# -------------------------
# Web Server Data State
# -------------------------
last_targets = []

# -------------------------
# Sensor Task
# -------------------------
async def sensor_task():
    global last_targets
    while True:
        if radar.update():
            last_targets = [
                {
                    "range": round(t.distance / 1000, 2),
                    "angle": round(t.angle, 1),
                    "speed": round(t.speed / 100.0, 2)
                }
                for t in radar.targets if t.distance > 0
            ]
        await asyncio.sleep(0.1)

# -------------------------
# Calibration Logic
# -------------------------
async def calibrate():
    print("Calibration started...")
    radar.targets = []
    await asyncio.sleep(0.2)
    print("Calibration complete.")

# -------------------------
# Web Interface (HTML)
# -------------------------
HTML = """<!DOCTYPE html>
<html>
<head>
  <title>RD-03D Radar</title>
  <style>
    body { margin: 0; background: #000; font-family: monospace; }
    canvas { display: block; }
    #infoPanel {
      position: fixed;
      top: 20px;
      left: 20px;
      color: #fff;
      font-family: monospace;
      background: rgba(0,0,0,0.4);
      padding: 10px;
      border: 1px solid #0f0;
    }
    .targetBlock {
      margin-bottom: 10px;
      padding: 5px;
      border-left: 5px solid;
    }
    #calibrateBtn {
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 10px 15px;
      background: #111;
      color: #0f0;
      font-size: 14px;
      font-family: monospace;
      border: 1px solid #0f0;
      cursor: pointer;
    }
    #calibrateBtn:hover {
      background: #0f0;
      color: #000;
    }
  </style>
</head>
<body>
  <canvas id="radar"></canvas>
  <div id="infoPanel"></div>
  <button id="calibrateBtn">Calibrate Now</button>

<script>
const canvas = document.getElementById('radar');
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;
const ctx = canvas.getContext('2d');
const centerX = canvas.width / 2;
const centerY = canvas.height * 0.85;
const scale = (centerY - 40) / 8;

const colors = ['#FF0000', '#0080FF', '#B400FF'];  // red, blue, purple
let targets = [];

function drawRadarBase() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = 'rgba(0, 0, 0, 0.1)';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.strokeStyle = '#00FF00';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(centerX, centerY, 8 * scale, -Math.PI/2 - Math.PI/3, -Math.PI/2 + Math.PI/3);
  ctx.stroke();

  // Triangle boundaries
  ctx.beginPath();
  ctx.moveTo(centerX, centerY);
  ctx.lineTo(centerX + Math.sin(Math.PI/3) * 8 * scale, centerY - Math.cos(Math.PI/3) * 8 * scale);
  ctx.moveTo(centerX, centerY);
  ctx.lineTo(centerX - Math.sin(Math.PI/3) * 8 * scale, centerY - Math.cos(Math.PI/3) * 8 * scale);
  ctx.stroke();

  // Distance rings
  ctx.strokeStyle = '#00FF0033';
  ctx.fillStyle = '#0f0';
  ctx.font = '12px monospace';
  for(let r = 1; r <= 8; r++) {
    ctx.beginPath();
    ctx.arc(centerX, centerY, r * scale, -Math.PI/2 - Math.PI/3, -Math.PI/2 + Math.PI/3);
    ctx.stroke();
    const labelAngle = -30 * Math.PI / 180;
    const labelX = centerX + (r * scale + 10) * Math.cos(labelAngle);
    const labelY = centerY + (r * scale + 10) * Math.sin(labelAngle);
    ctx.fillText(`${r}m`, labelX, labelY);
  }

  // Angle tick labels
  [-60, -30, 0, 30, 60].forEach(a => {
    const rad = a * Math.PI / 180;
    const x = centerX + Math.sin(rad) * 8 * scale;
    const y = centerY - Math.cos(rad) * 8 * scale;
    ctx.strokeStyle = '#00FF0022';
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(x, y);
    ctx.stroke();

    // Angle text
    const tx = centerX + Math.sin(rad) * (8 * scale + 25);
    const ty = centerY - Math.cos(rad) * (8 * scale + 25);
    ctx.fillStyle = '#0f0';
    ctx.fillText(`${a}°`, tx - 10, ty);
  });
}

function drawTargets() {
  const now = Date.now();
  targets.forEach((t, i) => {
    const angleRad = t.angle * Math.PI / 180;
    const targetX = centerX + t.range * scale * Math.sin(angleRad);
    const targetY = centerY - t.range * scale * Math.cos(angleRad);
    const color = colors[i % colors.length];

    // Speed trail
    const steps = 5;
    for (let s = 0; s < steps; s++) {
      const alpha = 1 - (s / (steps - 1)) * 0.8;
      const dotSize = 4 - (s / (steps - 1)) * 3.2;
      const distanceFactor = 50 * t.speed * ((s+1) / steps);
      const dx = Math.sin(angleRad) * distanceFactor;
      const dy = -Math.cos(angleRad) * distanceFactor;
      ctx.fillStyle = `rgba(${parseInt(color.substr(1,2), 16)}, ${parseInt(color.substr(3,2), 16)}, ${parseInt(color.substr(5,2), 16)}, ${alpha})`;
      ctx.beginPath();
      ctx.arc(targetX - dx, targetY - dy, dotSize, 0, Math.PI*2);
      ctx.fill();
    }

    // Main pulse dot
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(targetX, targetY, 8 + 2 * Math.sin(now / 200), 0, Math.PI * 2);
    ctx.fill();
  });
}

function updateInfoPanel() {
  const panel = document.getElementById('infoPanel');
  panel.innerHTML = '';
  targets.forEach((t, i) => {
    const block = document.createElement('div');
    block.className = 'targetBlock';
    block.style.borderColor = colors[i % colors.length];
    block.innerHTML = `
      <strong>Target ${i + 1}</strong><br>
      Angle: ${t.angle.toFixed(1)}°<br>
      Distance: ${t.range.toFixed(2)} m<br>
      Speed: ${(t.speed * 100).toFixed(2)} cm/s
    `;
    panel.appendChild(block);
  });
}

async function fetchData() {
  try {
    const res = await fetch('/data');
    const data = await res.json();
    if (Array.isArray(data.targets)) {
      targets = data.targets;
    } else if (data.target) {
      targets = [data.target];
    } else {
      targets = [];
    }
  } catch (e) {
    console.error("Fetch error:", e);
    targets = [];
  }
  setTimeout(fetchData, 100);
}

function animate() {
  drawRadarBase();
  drawTargets();
  updateInfoPanel();
  requestAnimationFrame(animate);
}

document.getElementById('calibrateBtn').addEventListener('click', () => {
  fetch('/calibrate').then(() => {
    console.log('Calibration triggered');
  }).catch(err => {
    console.error('Calibration failed:', err);
  });
});

fetchData();
animate();
</script>
</body>
</html>
"""

# -------------------------
# Web Server
# -------------------------
async def handle_client(reader, writer):
    try:
        request = await reader.read(1024)
        if b"GET /data" in request:
            response = f"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{json.dumps({'targets': last_targets})}"
        elif b"GET /calibrate" in request:
            await calibrate()
            response = "HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nCalibrated."
        else:
            response = f"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n{HTML}"
        await writer.awrite(response)
    except Exception as e:
        print("Client error:", e)
    finally:
        await writer.aclose()

async def web_server():
    server = await asyncio.start_server(handle_client, "0.0.0.0", 80)
    print("Web server running on port 80")
    await server.wait_closed()

async def main():
    asyncio.create_task(sensor_task())
    asyncio.create_task(web_server())
    while True:
        await asyncio.sleep(1)

asyncio.run(main())


