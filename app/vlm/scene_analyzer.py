import ollama

class SceneAnalyzer:
    def __init__(self, model="llava:7b"):
        self.model = model
        
    def analyze(self, image_path: str) -> str:
        """Analyze an image and return scene description"""
        
        response = ollama.chat(
            model=self.model,
            messages=[{
                "role": "user",
                "content": "Describe this traffic stop scene in one sentence. Focus on: officer position, officer actions, number of people visible.",
                "images": [image_path]
            }]
        )
        
        return response["message"]["content"]


if __name__ == "__main__":
    analyzer = SceneAnalyzer()
    result = analyzer.analyze("/Users/rayyan/Documents/GitHub/Power2ThePeople/app/vlm/policeimage.jpg")
    print(f"[VLM] {result}")
