import pandas as pd
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
import faiss
import json
from typing import List, Dict
import os

class TrafficStopRAG:
    def __init__(self, data_dir: str = "Data"):
        """
        Initialize the RAG system for traffic stop rights.

        Args:
            data_dir: Directory containing all the data files
        """
        self.data_dir = data_dir
        # self.model = SentenceTransformer(
        #     'nvidia/NV-Embed-v2',
        #     trust_remote_code=True,
        #     device='cuda',
        #     model_kwargs={
        #         'torch_dtype': torch.float32,  # Full precision, no quantization
        #     }
        # )
        self.model = SentenceTransformer('BAAI/bge-large-en-v1.5', device='cpu')
        self.index = None
        self.documents = []
        self.metadata = []
        
    def load_and_prepare_data(self):
        """Load all data sources and prepare them for RAG"""
        
        # 1. Load structured knowledge base from CSV
        csv_path = os.path.join(self.data_dir, "traffic_rights_structured.csv")
        df = pd.read_csv(csv_path)
        
        for _, row in df.iterrows():
            doc_text = f"""
            Title: {row['title']}
            Section: {row['section_heading']}
            
            Content: {row['content']}
            
            Source: {row['url']}
            """
            self.documents.append(doc_text.strip())
            self.metadata.append({
                'url': row['url'],
                'title': row['title'],
                'section': row['section_heading'],
                'type': 'knowledge_base'
            })
        
        # 2. Load training data from JSONL
        jsonl_path = os.path.join(self.data_dir, "traffic_rights_training.jsonl")
        with open(jsonl_path, 'r') as f:
            for line in f:
                data = json.loads(line)
                qa_text = f"""
                Question: {data['prompt']}
                
                Answer: {data['completion']}
                
                Scenario: {data['metadata'].get('scenario_type', 'general')}
                Source: {data['metadata'].get('source', 'unknown')}
                """
                self.documents.append(qa_text.strip())
                self.metadata.append({
                    'type': 'qa_pair',
                    'scenario': data['metadata'].get('scenario_type'),
                    'source': data['metadata'].get('source')
                })
        
        # 3. Load raw JSON for additional context
        json_path = os.path.join(self.data_dir, "traffic_rights_raw.json")
        with open(json_path, 'r') as f:
            raw_data = json.load(f)
        for item in raw_data:
            if 'sections' in item and item['sections']:
                for section in item['sections']:
                    if section.get('content'):
                        doc_text = f"""
                        Title: {item.get('title', 'Unknown')}
                        Section: {section.get('heading', 'General')}
                        
                        Content: {section['content']}
                        
                        Source: {item.get('url', 'unknown')}
                        """
                        self.documents.append(doc_text.strip())
                        self.metadata.append({
                            'url': item.get('url'),
                            'title': item.get('title'),
                            'section': section.get('heading'),
                            'type': 'raw_content'
                        })
        
        print(f"Loaded {len(self.documents)} documents from all sources")
        
    def build_index(self):
        """Create FAISS vector index from documents"""
        print("Creating embeddings...")
        embeddings = self.model.encode(self.documents, show_progress_bar=True)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings.astype('float32'))
        print(f"Built index with {self.index.ntotal} vectors")
        
    def search(self, query: str, k: int = 5, scenario_filter: str = None) -> List[Dict]:
        """Search for relevant documents"""
        query_embedding = self.model.encode([query])
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        scores, indices = self.index.search(query_embedding.astype('float32'), k * 2)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if scenario_filter and self.metadata[idx].get('scenario') != scenario_filter:
                continue
            results.append({
                'content': self.documents[idx],
                'score': float(score),
                'metadata': self.metadata[idx]
            })
            if len(results) >= k:
                break
        return results
    
    def generate_response(self, query: str, k: int = 3) -> Dict:
        """Generate a response based on top retrieved documents"""
        results = self.search(query, k=k)
        if not results:
            return {
                'answer': "I couldn't find relevant information for your query.",
                'sources': [],
                'confidence': 0.0
            }
        context = "\n\n---\n\n".join([r['content'] for r in results])
        avg_score = np.mean([r['score'] for r in results])
        sources = []
        for r in results:
            if r['metadata'].get('url') and r['metadata']['url'] not in sources:
                sources.append(r['metadata']['url'])
        return {
            'context': context,
            'sources': sources[:3],
            'confidence': float(avg_score),
            'num_results': len(results)
        }
    
    def save_index(self, path: str = "traffic_stop_rag.index"):
        faiss.write_index(self.index, path)
        with open(path + ".meta", 'w') as f:
            json.dump({'documents': self.documents, 'metadata': self.metadata}, f)
        print(f"Saved index to {path}")
    
    def load_index(self, path: str = "traffic_stop_rag.index"):
        self.index = faiss.read_index(path)
        with open(path + ".meta", 'r') as f:
            data = json.load(f)
            self.documents = data['documents']
            self.metadata = data['metadata']
        print(f"Loaded index with {len(self.documents)} documents")


def interactive_rag():
    """Interactive command-line interface"""
    print("Loading Traffic Stop Rights RAG System...")
    rag = TrafficStopRAG(data_dir="Data")
    
    try:
        rag.load_index()
        print("✓ Loaded existing index")
    except:
        print("Building new index...")
        rag.load_and_prepare_data()
        rag.build_index()
        rag.save_index()
    
    print("\n" + "="*80)
    print(" "*25 + "Traffic Stop Rights Assistant")
    print("="*80)
    print("Ask me anything about your rights during a traffic stop in California!")
    print("Type 'quit' to exit")
    print("="*80 + "\n")
    
    while True:
        query = input("💬 Your question: ").strip()
        if query.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Goodbye! Stay safe out there!")
            break
        if not query:
            continue
        print("\n🔍 Searching knowledge base...")
        response = rag.generate_response(query)
        print(f"\n📊 Confidence: {response['confidence']:.1%}")
        print(f"📄 Answer (based on {response['num_results']} sources):")
        print("─" * 80)
        print(response['context'])
        print("─" * 80)
        print("\n🔗 Sources:")
        for i, source in enumerate(response['sources'], 1):
            print(f"   {i}. {source}")
        print("\n" + "="*80 + "\n")


if __name__ == "__main__": 
    interactive_rag()
