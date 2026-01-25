from vlm.scene_analyzer import SceneAnalyzer
from llm.nemotron_client import NemotronClient

class Pipeline:
    def __init__(self):
        self.vlm = SceneAnalyzer()
        self.llm = NemotronClient()
        
    def run(self, image_path: str, transcript: str) -> dict:
        """Run the full pipeline"""
        
        # Step 1: Analyze image
        print("[1] Analyzing image...")
        scene = self.vlm.analyze(image_path)
        print(f"    Scene: {scene}")
        
        # Step 2: Generate advice
        print("[2] Generating advice...")
        advice = self.llm.generate_advice(scene, transcript)
        print(f"    Advice: {advice}")
        
        return {
            "scene": scene,
            "transcript": transcript,
            "advice": advice
        }


if __name__ == "__main__":
    pipeline = Pipeline()
    
    result = pipeline.run(
        image_path="/home/dell/traffic_stop.jpg",
        transcript="Mind if I take a look in your back seat?"
    )
    
    print("\n" + "="*50)
    print("FINAL OUTPUT")
    print("="*50)
    print(f"Scene: {result['scene']}")
    print(f"Officer said: {result['transcript']}")
    print(f"Advice: {result['advice']}")
