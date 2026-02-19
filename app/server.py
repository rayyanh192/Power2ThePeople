import os
import sys
import base64
import tempfile
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add the app directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vlm.scene_analyzer import SceneAnalyzer
from llm.nemotron_client import NemotronClient

app = FastAPI(title="Power2ThePeople API", version="1.0.0")

# Allow CORS for iOS app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize models on startup
scene_analyzer = None
nemotron_client = None


class AnalyzeRequest(BaseModel):
    transcript: str
    image: str  # base64 encoded JPEG


class AnalyzeResponse(BaseModel):
    advice: str
    scene: str


@app.on_event("startup")
async def startup_event():
    """Initialize models on server startup"""
    global scene_analyzer, nemotron_client
    print("Initializing models...")
    scene_analyzer = SceneAnalyzer()
    nemotron_client = NemotronClient(use_rag=True)
    print("Models ready!")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "models_loaded": scene_analyzer is not None}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Analyze a traffic stop scene and generate legal advice.

    - transcript: What the officer said
    - image: Base64 encoded JPEG image from glasses
    """
    if scene_analyzer is None or nemotron_client is None:
        raise HTTPException(status_code=503, detail="Models not loaded yet")

    # Decode base64 image and save to temp file
    try:
        image_data = base64.b64decode(request.image)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")

    # Save to temporary file (Ollama needs a file path)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
        tmp_file.write(image_data)
        tmp_path = tmp_file.name

    try:
        # Analyze scene with VLM
        print(f"[VLM] Analyzing image...")
        scene_description = scene_analyzer.analyze(tmp_path)
        print(f"[VLM] Scene: {scene_description}")

        # Generate advice with Nemotron + RAG
        print(f"[LLM] Generating advice for: {request.transcript[:50]}...")
        advice = nemotron_client.generate_advice(
            scene=scene_description,
            transcript=request.transcript
        )
        print(f"[LLM] Advice: {advice}")

        return AnalyzeResponse(advice=advice, scene=scene_description)

    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
