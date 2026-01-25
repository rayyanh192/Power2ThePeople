import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import json
from typing import List, Dict, Tuple
import os

class TrafficStopRAG:
    def __init__(self, data_dir: str = "Data"):
        """
        Initialize the RAG system for traffic stop rights.
        
        Args:
            data_dir: Directory containing all the data files
        """
        self.data_dir = data_dir
        self.model = SentenceTransformer('all-MiniLM-L6-v2')  # Fast, good embeddings
        self.index = None
        self.documents = []
        self.metadata = []
        
    def load_and_prepare_data(self):
        """Load all data sources and prepare them for RAG"""
        
        # 1. Load structured knowledge base from CSV
        csv_path = os.path.join(self.data_dir, "traffic_rights_structured.csv")
        df = pd.read_csv(csv_path)
        
        for _, row in df.iterrows():
            # Create rich document text
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
                # Add Q&A pairs as documents
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
        
        # Normalize embeddings for cosine similarity
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        
        # Create FAISS index
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)  # Inner product = cosine similarity
        self.index.add(embeddings.astype('float32'))
        
        print(f"Built index with {self.index.ntotal} vectors")
        
    def search(self, query: str, k: int = 5, scenario_filter: str = None) -> List[Dict]:
        """
        Search for relevant documents.
        
        Args:
            query: User's question
            k: Number of results to return
            scenario_filter: Optional scenario type to filter by
            
        Returns:
            List of relevant documents with metadata
        """
        # Encode query
        query_embedding = self.model.encode([query])
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        
        # Search
        scores, indices = self.index.search(query_embedding.astype('float32'), k * 2)
        
        # Filter and format results
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
        """
        Generate a response to a user query.
        
        Args:
            query: User's question
            k: Number of documents to retrieve
            
        Returns:
            Dictionary with response and sources
        """
        # Retrieve relevant documents
        results = self.search(query, k=k)
        
        if not results:
            return {
                'answer': "I couldn't find relevant information for your query.",
                'sources': [],
                'confidence': 0.0
            }
        
        # Combine top results into context
        context = "\n\n---\n\n".join([r['content'] for r in results])
        
        # Simple response generation (you can enhance this with an LLM)
        avg_score = np.mean([r['score'] for r in results])
        
        # Extract sources
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
        """Save the FAISS index to disk"""
        faiss.write_index(self.index, path)
        
        # Save documents and metadata
        with open(path + ".meta", 'w') as f:
            json.dump({
                'documents': self.documents,
                'metadata': self.metadata
            }, f)
        
        print(f"Saved index to {path}")
    
    def load_index(self, path: str = "traffic_stop_rag.index"):
        """Load the FAISS index from disk"""
        self.index = faiss.read_index(path)
        
        # Load documents and metadata
        with open(path + ".meta", 'r') as f:
            data = json.load(f)
            self.documents = data['documents']
            self.metadata = data['metadata']
        
        print(f"Loaded index with {len(self.documents)} documents")


class EnhancedTrafficStopRAG(TrafficStopRAG):
    """Enhanced RAG with statistical insights from stop data"""
    
    def __init__(self, data_dir: str = "Data"):
        super().__init__(data_dir)
        self.stop_data = None
        
    def load_stop_data(self):
        """Load and process police stop data"""
        csv_path = os.path.join(self.data_dir, "Police_Department_Stop_Data_20260124.csv")
        self.stop_data = pd.read_csv(csv_path)
        
        print(f"Loaded {len(self.stop_data)} police stop records")
        
    def get_stop_statistics(self, filters: Dict = None) -> Dict:
        """
        Get statistical insights from stop data.
        
        Args:
            filters: Dictionary of filters (e.g., {'year': 2023, 'reason': 'speeding'})
            
        Returns:
            Dictionary with statistics
        """
        if self.stop_data is None:
            self.load_stop_data()
        
        df = self.stop_data.copy()
        
        # Apply filters if provided
        if filters:
            for key, value in filters.items():
                if key in df.columns:
                    df = df[df[key] == value]
        
        stats = {
            'total_stops': len(df),
            'unique_locations': df['location'].nunique() if 'location' in df.columns else 0,
            'most_common_reasons': df['reason'].value_counts().head(5).to_dict() if 'reason' in df.columns else {},
            'stops_by_time_of_day': self._analyze_time_patterns(df) if 'time' in df.columns else {}
        }
        
        return stats
    
    def _analyze_time_patterns(self, df: pd.DataFrame) -> Dict:
        """Analyze patterns by time of day"""
        if 'time' not in df.columns:
            return {}
        
        # This is a simplified version - adjust based on actual data format
        time_categories = {
            'morning': 0,
            'afternoon': 0,
            'evening': 0,
            'night': 0
        }
        
        return time_categories
    
    def enhanced_search(self, query: str, include_stats: bool = True) -> Dict:
        """
        Enhanced search that combines RAG with statistical insights.
        
        Args:
            query: User's question
            include_stats: Whether to include relevant statistics
            
        Returns:
            Enhanced response with context and stats
        """
        # Get RAG response
        rag_response = self.generate_response(query, k=3)
        
        # Add statistical context if relevant
        if include_stats:
            # Detect if query is about specific scenarios
            scenario_keywords = {
                'speeding': 'speeding',
                'dui': 'DUI',
                'license': 'license',
                'search': 'search'
            }
            
            detected_scenario = None
            for keyword, scenario in scenario_keywords.items():
                if keyword.lower() in query.lower():
                    detected_scenario = scenario
                    break
            
            if detected_scenario and self.stop_data is not None:
                try:
                    stats = self.get_stop_statistics({'reason': detected_scenario})
                    rag_response['statistics'] = stats
                except:
                    pass
        
        return rag_response


def interactive_rag():
    """Interactive command-line interface for the RAG system"""
    print("Loading Traffic Stop Rights RAG System...")
    rag = EnhancedTrafficStopRAG(data_dir="Data")
    
    # Try to load existing index
    try:
        rag.load_index()
        print("✓ Loaded existing index")
    except:
        print("Building new index...")
        rag.load_and_prepare_data()
        rag.build_index()
        rag.save_index()
    
    # Load stop data
    try:
        rag.load_stop_data()
        print("✓ Loaded police stop data")
    except Exception as e:
        print(f"⚠ Could not load stop data: {e}")
    
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
        response = rag.enhanced_search(query)
        
        print(f"\n📊 Confidence: {response['confidence']:.1%}")
        print(f"📄 Answer (based on {response['num_results']} sources):")
        print("─" * 80)
        print(response['context'])
        print("─" * 80)
        
        if response.get('statistics'):
            print("\n📈 Relevant Statistics:")
            stats = response['statistics']
            if 'total_stops' in stats:
                print(f"   Total stops in dataset: {stats['total_stops']:,}")
            if 'most_common_reasons' in stats and stats['most_common_reasons']:
                print("   Most common reasons:")
                for reason, count in stats['most_common_reasons'].items():
                    print(f"      • {reason}: {count:,}")
        
        print(f"\n🔗 Sources:")
        for i, source in enumerate(response['sources'], 1):
            print(f"   {i}. {source}")
        
        print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    interactive_rag()