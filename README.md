# NSE FII/DII Data API

> Drop-in REST API that fetches FII/DII data directly from NSE India.  
> Your backend just hits `GET /api/v1/fii-dii/today` — that's it.

---

## Quick Start

### Option 1: Run Directly
```bash
pip install fastapi uvicorn requests
python main.py
# Server starts at http://localhost:8000
```

### Option 2: Docker
```bash
docker build -t nse-fii-dii-api .
docker run -d -p 8000:8000 --name fii-dii nse-fii-dii-api
```

### Option 3: Docker Compose (if you want to add it to existing stack)
```yaml
services:
  fii-dii-api:
    build: .
    ports:
      - "8000:8000"
    restart: unless-stopped
```

---

## API Endpoints

### 1. GET `/api/v1/fii-dii/today`  ← **Main Endpoint**

Returns today's FII/DII data. This is the only endpoint your backend needs to consume.

**Query Params:**
| Param    | Type | Default | Description |
|----------|------|---------|-------------|
| refresh  | bool | false   | Force fresh fetch from NSE (bypasses 5-min cache) |

**Sample Request:**
```bash
curl http://your-server:8000/api/v1/fii-dii/today
```

**Sample Response (200 OK):**
```json
{
  "status": "success",
  "source": "NSE India (nseindia.com/api/fiidiiTradeReact)",
  "fetched_at": "2026-03-20T17:32:15.123456",
  "data_date": "20-Mar-2026",
  "fii": {
    "date": "20-Mar-2026",
    "buy_value_cr": 15234.56,
    "sell_value_cr": 12876.43,
    "net_value_cr": 2358.13,
    "net_action": "NET_BUYER"
  },
  "dii": {
    "date": "20-Mar-2026",
    "buy_value_cr": 9876.54,
    "sell_value_cr": 11234.56,
    "net_value_cr": -1358.02,
    "net_action": "NET_SELLER"
  }
}
```

**Error Response (503 - Data not available):**
```json
{
  "detail": {
    "status": "error",
    "error": "NSE_FETCH_FAILED",
    "message": "Unable to fetch data from NSE. This usually means: (1) data is not yet published (before ~5 PM IST), (2) NSE is temporarily unreachable, or (3) rate limit hit. Try again in a few minutes.",
    "timestamp": "2026-03-20T16:45:00.000000"
  }
}
```

### 2. GET `/api/v1/fii-dii/raw`

Returns raw unprocessed JSON from NSE (useful for debugging).

```json
{
  "status": "success",
  "fetched_at": "2026-03-20T17:32:15.123456",
  "nse_raw_response": [
    {
      "category": "FII/FPI *",
      "date": "20-Mar-2026",
      "buyValue": "15,234.56",
      "sellValue": "12,876.43",
      "netValue": "2,358.13"
    },
    {
      "category": "DII *",
      "date": "20-Mar-2026",
      "buyValue": "9,876.54",
      "sellValue": "11,234.56",
      "netValue": "-1,358.02"
    }
  ]
}
```

### 3. GET `/api/v1/fii-dii/health`

Health check for monitoring/load balancers.

```json
{
  "status": "healthy",
  "service": "nse-fii-dii-api",
  "cache_status": "warm",
  "cache_age_seconds": 142,
  "last_data_date": "20-Mar-2026",
  "timestamp": "2026-03-20T17:34:37.000000"
}
```

### 4. Swagger Docs

Interactive API docs available at: `http://your-server:8000/docs`

---

## How to Consume from Your Backend

### Java / Spring Boot
```java
RestTemplate restTemplate = new RestTemplate();
String url = "http://fii-dii-service:8000/api/v1/fii-dii/today";

ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
Map<String, Object> data = response.getBody();

Map<String, Object> fii = (Map) data.get("fii");
double fiiNetValue = (double) fii.get("net_value_cr");
String fiiAction = (String) fii.get("net_action"); // "NET_BUYER" or "NET_SELLER"
```

### Node.js
```javascript
const response = await fetch('http://fii-dii-service:8000/api/v1/fii-dii/today');
const data = await response.json();

console.log(data.fii.net_value_cr);    // 2358.13
console.log(data.fii.net_action);      // "NET_BUYER"
console.log(data.dii.net_value_cr);    // -1358.02
```

### Python
```python
import requests
data = requests.get("http://fii-dii-service:8000/api/v1/fii-dii/today").json()

fii_net = data["fii"]["net_value_cr"]
dii_net = data["dii"]["net_value_cr"]
```

### cURL (for testing)
```bash
# Basic fetch
curl http://localhost:8000/api/v1/fii-dii/today

# Force refresh (skip cache)
curl http://localhost:8000/api/v1/fii-dii/today?refresh=true

# Pretty print
curl -s http://localhost:8000/api/v1/fii-dii/today | python3 -m json.tool
```

---

## Response Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | "success" or "error" |
| `source` | string | Always "NSE India (...)" |
| `fetched_at` | string (ISO) | When this data was fetched from NSE |
| `data_date` | string | Trading date (e.g. "20-Mar-2026") |
| `fii.buy_value_cr` | float | FII/FPI total buy value in ₹ Crores |
| `fii.sell_value_cr` | float | FII/FPI total sell value in ₹ Crores |
| `fii.net_value_cr` | float | FII/FPI net = buy - sell (₹ Crores) |
| `fii.net_action` | string | "NET_BUYER" / "NET_SELLER" / "NEUTRAL" |
| `dii.buy_value_cr` | float | DII total buy value in ₹ Crores |
| `dii.sell_value_cr` | float | DII total sell value in ₹ Crores |
| `dii.net_value_cr` | float | DII net = buy - sell (₹ Crores) |
| `dii.net_action` | string | "NET_BUYER" / "NET_SELLER" / "NEUTRAL" |

---

## Architecture

```
NSE Website (nseindia.com/reports/fii-dii)
    │
    │  Internal JSON API
    ▼
nseindia.com/api/fiidiiTradeReact  ──→  Returns JSON
    │
    │  Python (requests + session cookies)
    ▼
┌────────────────────────────────┐
│  This FastAPI Service          │
│  - Fetches from NSE            │
│  - Parses & structures data    │
│  - Caches for 5 min            │
│  - Serves via REST API         │
│  Port: 8000                    │
└────────────────────────────────┘
    │
    │  GET /api/v1/fii-dii/today
    ▼
Your Backend
```

## Key Design Decisions

1. **5-minute cache**: Prevents hammering NSE. Multiple requests within 5 min get cached response.
2. **Graceful degradation**: If NSE is unreachable, serves stale cache with a warning flag.
3. **Retry with backoff**: 3 attempts with increasing delays (5s, 10s).
4. **Session cookie handling**: NSE blocks cookieless requests. The service mimics a browser session.
5. **Thread-safe cache**: Safe for concurrent requests from multiple consumers.

## Important Notes

- **Data availability**: NSE publishes FII/DII data between ~5:00-5:30 PM IST. Before that, the API returns 503.
- **Market holidays**: No data published on holidays. API returns stale data or 503.
- **Rate limits**: Don't call with `?refresh=true` more than a few times per hour.
- **IP**: Deploy on a server with an Indian IP for best reliability.
- **Monitoring**: Use `/api/v1/fii-dii/health` for your load balancer / uptime checks.
