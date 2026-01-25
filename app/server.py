import os
import sys
import uuid
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Header
from fastapi.responses import JSONResponse
import uvicorn
from typing import Optional

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from vlm.scene_analyzer import SceneAnalyzer
from llm.nemotron_client import NemotronClient

# Configuration
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "your-secret-token-here")
TMP_DIR = "/tmp"

# Initialize components
print("Initializing SceneAnalyzer and NemotronClient...")
scene_analyzer = SceneAnalyzer(model="llava")

# Initialize NemotronClient with RAG
rag_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rag')
data_dir = os.path.join(rag_dir, 'Data')
index_path = os.path.join(rag_dir, 'traffic_stop_rag.index')

client = NemotronClient(
    model="nemotron:70b-fast",
    use_rag=True,
    data_dir=data_dir,
    index_path=index_path
)

print("✓ Server components initialized")

# FastAPI app
app = FastAPI(title="Power2ThePeople API", version="1.0.0")


@app.post("/ingest")
async def ingest(
    transcript: str = Form(...),
    image: UploadFile = File(...),
    x_auth_token: Optional[str] = Header(None)
):
    """
    Ingest a traffic stop transcript and image, return legal advice.

    Args:
        transcript: What the officer said
        image: JPEG image file from the scene
        x_auth_token: Authentication token (header)

    Returns:
        JSON: {"advice": "...", "scene_description": "..."}
    """

    # Authentication check
    if x_auth_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing authentication token")

    # Validate image type
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        # Save image to /tmp with unique filename
        image_filename = f"traffic_stop_{uuid.uuid4().hex}.jpg"
        image_path = os.path.join(TMP_DIR, image_filename)

        with open(image_path, "wb") as f:
            contents = await image.read()
            f.write(contents)

        print(f"[SERVER] Saved image to {image_path}")
        print(f"[SERVER] Processing transcript: {transcript[:50]}...")

        # Step 1: Analyze scene with VLM
        scene_description = scene_analyzer.analyze(image_path)
        print(f"[SERVER] Scene analyzed: {scene_description}")

        # Step 2: Generate advice with NemotronClient
        advice = client.generate_advice(
            scene=scene_description,
            transcript=transcript
        )
        print(f"[SERVER] Advice generated: {advice}")

        # Cleanup: optionally remove the temp file
        # os.remove(image_path)

        return JSONResponse(content={
            "advice": advice,
            "scene_description": scene_description
        })

    except Exception as e:
        print(f"[SERVER ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "message": "Power2ThePeople API is running"}


if __name__ == "__main__":
    print("\n" + "="*80)
    print("POWER2THEPEOPLE - FASTAPI SERVER")
    print("="*80)
    print(f"Authentication token: {AUTH_TOKEN}")
    print(f"Temporary image directory: {TMP_DIR}")
    print("="*80 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
