#!/usr/bin/env python3
"""
Test client for Power2ThePeople FastAPI server
"""

import requests
import sys
import os

# Configuration
SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8000")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "your-secret-token-here")

def test_ingest(image_path: str, transcript: str):
    """Test the /ingest endpoint"""

    if not os.path.exists(image_path):
        print(f"Error: Image not found at {image_path}")
        return

    print("="*80)
    print("TESTING /ingest ENDPOINT")
    print("="*80)
    print(f"Server: {SERVER_URL}")
    print(f"Image: {image_path}")
    print(f"Transcript: {transcript}")
    print("="*80 + "\n")

    try:
        with open(image_path, 'rb') as f:
            files = {'image': ('traffic_stop.jpg', f, 'image/jpeg')}
            data = {'transcript': transcript}
            headers = {'X-Auth-Token': AUTH_TOKEN}

            response = requests.post(
                f"{SERVER_URL}/ingest",
                files=files,
                data=data,
                headers=headers,
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                print("✓ SUCCESS\n")
                print(f"Scene Description:\n{result['scene_description']}\n")
                print(f"Legal Advice:\n{result['advice']}\n")
            else:
                print(f"✗ ERROR {response.status_code}")
                print(f"Response: {response.text}")

    except requests.exceptions.ConnectionError:
        print(f"✗ CONNECTION ERROR: Could not connect to {SERVER_URL}")
        print("Make sure the server is running with: python server.py")
    except Exception as e:
        print(f"✗ ERROR: {str(e)}")


def test_health():
    """Test the /health endpoint"""
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"✓ Server is healthy: {response.json()}")
        else:
            print(f"✗ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"✗ Cannot reach server: {str(e)}")


if __name__ == "__main__":
    # Test health first
    print("Testing server health...")
    test_health()
    print()

    # Test ingest endpoint
    if len(sys.argv) >= 3:
        image_path = sys.argv[1]
        transcript = sys.argv[2]
    else:
        # Default test case
        image_path = "/home/dell/traffic_stop.jpg"
        transcript = "I need to see your license and registration"
        print(f"Usage: {sys.argv[0]} <image_path> <transcript>")
        print(f"Using defaults: {image_path} + \"{transcript}\"\n")

    test_ingest(image_path, transcript)
