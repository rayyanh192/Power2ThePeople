import ollama

class NemotronClient:
    def __init__(self, model="nemotron-mini"):
        self.model = model
        
    def generate_advice(self, scene: str, transcript: str) -> str:
        """Generate legal advice based on scene and transcript"""
        
        prompt = f"""You are a legal rights assistant helping a DRIVER during a police traffic stop.

You are advising the DRIVER, not the officer. Your job is to help the driver understand and protect their constitutional rights.

Scene: {scene}
Officer said: "{transcript}"

Key legal facts:
- The 4th Amendment protects against unreasonable searches
- Drivers can legally refuse consent to search their vehicle
- Refusing a search is not suspicious and cannot be used against you

Give the DRIVER brief advice in under 15 words. Help them protect their rights."""

        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response["message"]["content"]


if __name__ == "__main__":
    client = NemotronClient()
    result = client.generate_advice(
        scene="Officer standing at driver window",
        transcript="Mind if I take a look in your back seat?"
    )
    print(f"[NEMOTRON] {result}")
