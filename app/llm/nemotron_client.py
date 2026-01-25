import ollama
import sys
import os

# Add the parent directory to the path to import RAG
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag.rag import TrafficStopRAG

class NemotronClient:
    def __init__(self, model="nemotron-mini", use_rag=True, data_dir="Data", index_path=None):
        self.model = model
        self.use_rag = use_rag

        # Initialize RAG system
        if self.use_rag:
            print("Initializing RAG system...")
            self.rag = TrafficStopRAG(data_dir=data_dir)
            try:
                # If no index path provided, construct the default path relative to the rag module
                if index_path is None:
                    rag_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rag')
                    index_path = os.path.join(rag_dir, 'traffic_stop_rag.index')

                self.rag.load_index(index_path)
                print("✓ RAG system loaded successfully")
            except Exception as e:
                print(f"Warning: Could not load RAG index: {e}")
                print("RAG system will be disabled for this session")
                self.use_rag = False
        else:
            self.rag = None
        
    def generate_advice(self, scene: str, transcript: str) -> str:
        """Generate legal advice based on scene and transcript"""

        # Query RAG for relevant legal context
        legal_context = ""
        if self.use_rag and self.rag:
            # Create a query from the scene and transcript
            rag_query = f"What are my rights when a police officer says: '{transcript}' during a traffic stop? Scene: {scene}"

            print(f"[RAG] Querying: {rag_query[:100]}...")
            rag_response = self.rag.generate_response(rag_query, k=3)

            if rag_response['confidence'] > 0.3:  # Only use if confidence is reasonable
                legal_context = f"\n\nRelevant Legal Information (from legal sources):\n{rag_response['context']}\n"
                print(f"[RAG] Retrieved context with {rag_response['confidence']:.1%} confidence from {rag_response['num_results']} sources")
            else:
                print(f"[RAG] Low confidence ({rag_response['confidence']:.1%}), using fallback knowledge")

        # Build prompt with RAG context if available
        if legal_context:
            prompt = f"""You are a legal rights assistant helping a DRIVER during a police traffic stop.

You are advising the DRIVER, not the officer. Your job is to help the driver understand and protect their constitutional rights.

Scene: {scene}
Officer said: "{transcript}"
{legal_context}

Based on the legal information above, give the DRIVER brief, actionable advice in under 15 words. Help them protect their rights."""
        else:
            # Fallback to original prompt if RAG is unavailable
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
    print("="*80)
    print("Nemotron Client with RAG Integration Test")
    print("="*80)

    # Initialize client with RAG
    client = NemotronClient(use_rag=True)

    print("\n" + "-"*80)
    print("Test Case: Officer requests to search vehicle")
    print("-"*80)

    result = client.generate_advice(
        scene="Officer standing at driver window",
        transcript="Mind if I take a look in your back seat?"
    )

    print(f"\n[NEMOTRON ADVICE] {result}")
    print("="*80)
