
from datetime import date
import os
import secrets

import pandas as pd
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Smart Retail Inventory API")

API_KEY = os.getenv("API_KEY", "demo-change-this-key")
LEAD_TIME_DAYS = 4
SAFETY_STOCK = 5
TARGET_STOCK = 30

# Sample historical sales: replace with actual shop data later.
SAMPLE_SALES = {
    "Shampoo": [3,4,2,5,3,4,6,3,5,4,2,4,5,3,4,6,3,5,4,3,5,4,6,3,4,5,2,4,6,3],
    "Soap": [5,4,6,5,3,6,7,4,5,6,4,5,7,3,6,5,4,7,5,6,4,5,6,7,3,5,6,4,7,5],
    "Conditioner": [2,3,2,4,3,2,4,3,5,2,3,4,2,3,5,2,4,3,2,4,3,5,2,4,3,2,4,5,3,2],
    "Lotion": [2,2,3,1,3,2,4,2,3,2,1,3,2,2,4,3,2,3,1,2,3,2,4,2,3,1,2,3,2,3],
    "Face Wash": [2,3,2,3,1,2,4,2,3,2,3,1,2,3,4,2,3,2,1,3,2,4,2,3,1,2,3,4,2,3],
    "Detergent": [2,3,2,4,3,2,3,4,2,3,2,4,3,2,5,3,2,3,4,2,3,4,2,3,5,2,3,4,2,3]
}

def forecast_product(product):
    if product not in SAMPLE_SALES:
        raise HTTPException(status_code=404, detail="Unknown product")
    sales = pd.Series(SAMPLE_SALES[product], dtype=float)

    # Test on last 7 days, using only each day's previous 7 days.
    errors = []
    for i in range(len(sales) - 7, len(sales)):
        prediction = sales.iloc[i-7:i].mean()
        errors.append(abs(sales.iloc[i] - prediction))

    return {
        "predicted_daily_demand": round(float(sales.tail(7).mean()), 2),
        "mae": round(float(sum(errors) / len(errors)), 2)
    }

class StockReading(BaseModel):
    uid: str
    product: str
    weight_kg: float = Field(ge=0, le=1000)
    quantity: int = Field(ge=0, le=100000)

latest_inventory = {}

def calculate_inventory(reading):
    forecast = forecast_product(reading.product)
    demand = forecast["predicted_daily_demand"]
    reorder_point = demand * LEAD_TIME_DAYS + SAFETY_STOCK

    return {
        "uid": reading.uid,
        "product": reading.product,
        "weight_kg": round(reading.weight_kg, 3),
        "current_stock": reading.quantity,
        "predicted_daily_demand": demand,
        "mae": forecast["mae"],
        "reorder_point": round(reorder_point, 2),
        "suggested_order": max(0, TARGET_STOCK - reading.quantity),
        "status": "REORDER REQUIRED" if reading.quantity <= reorder_point else "Stock sufficient",
        "updated_at": date.today().isoformat()
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "Smart Retail Inventory API"}

@app.get("/api/inventory")
def get_inventory():
    return list(latest_inventory.values())

@app.post("/api/stock")
def receive_stock(reading: StockReading, x_api_key: str = Header(default="")):
    if not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    result = calculate_inventory(reading)
    latest_inventory[reading.product] = result
    return result

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Smart Retail Inventory</title>
      <style>
        body {font-family:Arial;margin:24px;background:#f3f6f9;color:#17202a}
        table {border-collapse:collapse;width:100%;background:white}
        th,td {padding:10px;border-bottom:1px solid #ddd;text-align:left}
        th {background:#e8edf2}
      </style>
    </head>
    <body>
      <h1>Smart Retail Inventory Dashboard</h1>
      <p id="msg">Waiting for ESP32 stock readings...</p>
      <table>
      <thead><tr><th>Product</th><th>Stock</th><th>Weight kg</th>
      <th>Demand/day</th><th>MAE</th><th>Reorder point</th>
      <th>Suggested order</th><th>Status</th></tr></thead>
      <tbody id="rows"></tbody></table>
      <script>
      async function refresh() {
        try {
          const r = await fetch('/api/inventory');
          const items = await r.json();
          const rows = document.getElementById('rows');
          rows.replaceChildren();
          for (const x of items) {
            const tr = document.createElement('tr');
            for (const v of [x.product,x.current_stock,x.weight_kg,
              x.predicted_daily_demand,x.mae,x.reorder_point,
              x.suggested_order,x.status]) {
              const td = document.createElement('td');
              td.textContent = v;
              tr.appendChild(td);
            }
            rows.appendChild(tr);
          }
          document.getElementById('msg').textContent =
            items.length ? 'Dashboard updated: ' + new Date().toLocaleTimeString()
            : 'No readings received yet. Start Wokwi and scan an RFID tag.';
        } catch(e) {
          document.getElementById('msg').textContent = 'Unable to load data.';
        }
      }
      refresh();
      setInterval(refresh, 5000);
      </script>
    </body>
    </html>
    """
