# Power2ThePeople FastAPI Server

RESTful API server for the Power2ThePeople traffic stop legal rights assistant.

## Features

- **POST /ingest** - Process traffic stop scenes with transcript + image
- **GET /health** - Health check endpoint
- Authentication via `X-Auth-Token` header
- Integrates VLM (llava) for scene analysis
- Uses NemotronClient with RAG for legal advice generation

## Setup

### 1. Install Dependencies

```bash
cd /home/dell/Power2ThePeople/app
pip install -r requirements_server.txt
```

### 2. Set Authentication Token

```bash
export AUTH_TOKEN="your-secret-token-here"
```

Or edit the token directly in [server.py](server.py:16)

### 3. Start the Server

```bash
cd /home/dell/Power2ThePeople/app
python server.py
```

The server will start on `http://0.0.0.0:8000`

## API Endpoints

### POST /ingest

Process a traffic stop scene with image and transcript.

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Headers: `X-Auth-Token: your-secret-token-here`
- Body:
  - `transcript` (string) - What the officer said
  - `image` (file) - JPEG image of the scene

**Response:**
```json
{
  "advice": "You can refuse the search. Say 'I do not consent to searches.'",
  "scene_description": "Officer standing at driver window, making request"
}
```

**Example with curl:**
```bash
curl -X POST http://localhost:8000/ingest \
  -H "X-Auth-Token: your-secret-token-here" \
  -F "transcript=Can I search your vehicle?" \
  -F "image=@/path/to/traffic_stop.jpg"
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "message": "Power2ThePeople API is running"
}
```

## Testing

### Using the Test Client

```bash
# Test with default image and transcript
python test_client.py

# Test with custom image and transcript
python test_client.py /path/to/image.jpg "Can I search your car?"
```

### Using curl

```bash
# Health check
curl http://localhost:8000/health

# Ingest endpoint
curl -X POST http://localhost:8000/ingest \
  -H "X-Auth-Token: your-secret-token-here" \
  -F "transcript=Step out of the vehicle" \
  -F "image=@/home/dell/traffic_stop.jpg"
```

## Tailscale Setup for Phone Access

1. **Get your DGX Tailscale IP:**
   ```bash
   tailscale ip -4
   ```

2. **Configure phone app to POST to:**
   ```
   http://[YOUR_TAILSCALE_IP]:8000/ingest
   ```

3. **Set AUTH_TOKEN in phone app**

4. **Ensure Tailscale is running on DGX:**
   ```bash
   sudo tailscale up
   ```

## Architecture

```
Phone (Ray-Ban Meta / Camera)
    ↓ HTTP POST (image + transcript)
Tailscale Network
    ↓
DGX Server (FastAPI)
    ↓
SceneAnalyzer (llava VLM)
    ↓
NemotronClient (RAG + Ollama)
    ↓ JSON Response
Phone displays advice
```

## Configuration

Environment variables:
- `AUTH_TOKEN` - Authentication token (default: "your-secret-token-here")
- `SERVER_URL` - For test client (default: "http://localhost:8000")

## Troubleshooting

**Server won't start:**
- Check if port 8000 is already in use: `lsof -i :8000`
- Try a different port: Edit [server.py:117](server.py:117)

**401 Unauthorized:**
- Check `X-Auth-Token` header matches server's `AUTH_TOKEN`

**500 Internal Server Error:**
- Check Ollama is running: `ollama list`
- Check models are available: `ollama list` should show `llava` and `nemotron:70b-fast`
- Check RAG index exists: `/home/dell/Power2ThePeople/app/rag/traffic_stop_rag.index`

**Connection refused from phone:**
- Verify Tailscale is running on both devices
- Check firewall allows port 8000
- Test with curl from another device on Tailscale network
