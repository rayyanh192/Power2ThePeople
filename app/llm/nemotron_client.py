import ollama
import sys
import os
import pandas as pd
from collections import Counter
import math
import re
import time
import threading
import termios
import tty

# Add the parent directory to the path to import RAG
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag.rag import TrafficStopRAG
from vlm.scene_analyzer import SceneAnalyzer


class StopDataAnalyzer:
    def __init__(self, csv_path: str):
        """Analyze historical traffic stop data"""
        print(f"Loading stop data from {csv_path}...")
        self.df = pd.read_csv(csv_path, low_memory=False)
        self._preprocess_data()
        print(f"✓ Loaded {len(self.df)} stop records")

    def _preprocess_data(self):
        """Clean and prepare the data"""
        # Fill missing values
        for col in ['incident_location', 'analysis_neighborhood', 'allegation_summary', 'dpa_finding', ' point']:
            if col in self.df.columns:
                self.df[col] = self.df[col].fillna('')

        # Extract lat/lon from POINT column
        self.df['latitude'] = None
        self.df['longitude'] = None

        if ' point' in self.df.columns:
            for idx, row in self.df.iterrows():
                point_str = str(row[' point'])
                if 'POINT' in point_str:
                    coords = re.findall(r'[-\d.]+', point_str)
                    if len(coords) >= 2:
                        self.df.at[idx, 'longitude'] = float(coords[0])
                        self.df.at[idx, 'latitude'] = float(coords[1])

        print(f"✓ Extracted coordinates for {self.df['latitude'].notna().sum()} records")

    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance in miles between two coordinates"""
        R = 3959
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    def get_coords_from_location(self, location_name: str):
        """Get coordinates from location name using Nominatim API"""
        import requests
        import time

        search_query = f"{location_name}, San Francisco, CA"
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': search_query,
            'format': 'json',
            'limit': 1,
            'viewbox': '-122.52,37.83,-122.35,37.70',
            'bounded': 1
        }
        headers = {'User-Agent': 'TrafficStopApp/1.0'}

        try:
            time.sleep(1)
            response = requests.get(url, params=params, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data:
                    lat, lon = float(data[0]['lat']), float(data[0]['lon'])
                    if 37.70 <= lat <= 37.83 and -122.52 <= lon <= -122.35:
                        return lat, lon
        except Exception as e:
            print(f"Geocoding error: {e}")

        return None

    def analyze_location_by_coords(self, user_lat: float, user_lon: float, radius_miles: float = 0.25):
        """Analyze patterns near specific coordinates"""
        df_with_coords = self.df[self.df['latitude'].notna() & self.df['longitude'].notna()].copy()

        if len(df_with_coords) == 0:
            return {'found_data': False, 'message': "No location data available for analysis."}

        df_with_coords['distance'] = df_with_coords.apply(
            lambda row: self.haversine_distance(user_lat, user_lon, row['latitude'], row['longitude']),
            axis=1
        )

        nearby = df_with_coords[df_with_coords['distance'] <= radius_miles]
        total_stops = len(nearby)

        if total_stops == 0:
            return {'found_data': False, 'message': f"No incidents found within {radius_miles} miles."}

        allegations = nearby['allegation_summary'].dropna()
        allegation_counts = Counter()
        for allegation in allegations:
            if allegation and len(str(allegation)) > 5:
                allegation_counts[str(allegation)] += 1

        findings = nearby['dpa_finding'].dropna()
        finding_counts = Counter(findings)

        sustained_misconduct = len(nearby[
            nearby['dpa_finding'].astype(str).str.contains('Sustained', case=False, na=False)
        ])

        improper_conduct = len(nearby[
            nearby['allegation_summary'].astype(str).str.contains(
                'improper|inappropriate|misconduct|excessive|unlawful',
                case=False, na=False, regex=True
            )
        ])

        closest = nearby.nsmallest(1, 'distance').iloc[0] if len(nearby) > 0 else None

        return {
            'found_data': True,
            'total_stops': total_stops,
            'radius_miles': radius_miles,
            'closest_distance': closest['distance'] if closest is not None else None,
            'top_allegations': allegation_counts.most_common(3),
            'sustained_misconduct': sustained_misconduct,
            'improper_conduct': improper_conduct,
            'finding_counts': dict(finding_counts.most_common(5))
        }

    def analyze_location(self, location_name: str, radius_miles: float = 0.25):
        """Analyze patterns for a location"""
        coords = self.get_coords_from_location(location_name)
        if coords:
            lat, lon = coords
            print(f"📍 Found coordinates: {lat:.6f}, {lon:.6f}")
            return self.analyze_location_by_coords(lat, lon, radius_miles)

        return {'found_data': False, 'message': f"Could not locate {location_name} in San Francisco."}

    def generate_summary(self, analysis: dict, reason: str = None) -> str:
        """Generate summary of misconduct data"""
        if not analysis['found_data']:
            return analysis['message']

        parts = []
        parts.append(f"📊 Within {analysis['radius_miles']} miles of your location:")
        parts.append(f"   Historical complaints: {analysis['total_stops']}")

        if analysis['sustained_misconduct'] > 0:
            parts.append(f"   ⚠️ WARNING: {analysis['sustained_misconduct']} sustained misconduct findings")

        if analysis['improper_conduct'] > 0:
            parts.append(f"   ⚠️ {analysis['improper_conduct']} complaints about improper/unlawful conduct")

        if analysis['top_allegations']:
            parts.append("\n   Most common allegations:")
            for allegation, count in analysis['top_allegations']:
                parts.append(f"     • {allegation} ({count} cases)")

        if reason:
            parts.append(f"\n   You were stopped for: {reason}")

        return "\n".join(parts)

    def parse_pullover_input(self, text: str):
        """Extract location and reason from input like 'speeding on main street'"""
        location = None
        reason = None

        if " at " in text.lower():
            location = text.lower().split(" at ")[1].split(" for ")[0].strip()
        elif " on " in text.lower():
            location = text.lower().split(" on ")[1].split(" for ")[0].strip()

        if " for " in text.lower():
            reason = text.lower().split(" for ")[1].strip()
        else:
            # If no "for", assume the whole thing before location is the reason
            if " on " in text.lower():
                reason = text.lower().split(" on ")[0].strip()
            elif " at " in text.lower():
                reason = text.lower().split(" at ")[0].strip()

        return location, reason


class NemotronClient:
    def __init__(self, model="nemotron:70b-fast", use_rag=True, data_dir="Data", index_path=None):
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

        print("Warming up model...")
        ollama.chat(model=self.model, messages=[{"role": "user", "content": "Hi"}])
        print("✓ Model ready")
        
    def generate_advice(self, scene: str, transcript: str) -> str:
        """Generate legal advice based on scene and transcript"""

        # Query RAG for relevant legal context
        legal_context = ""
        if self.use_rag and self.rag:
            rag_query = f"What are my rights when a police officer says: '{transcript}' during a traffic stop? Scene: {scene}"

            print(f"[RAG] Querying: {rag_query[:100]}...")
            rag_response = self.rag.generate_response(rag_query, k=1)

            if rag_response['confidence'] > 0.3:
                legal_context = f"\n\nRelevant Legal Information:\n{rag_response['context']}\n"
                print(f"[RAG] Retrieved context with {rag_response['confidence']:.1%} confidence")
            else:
                print(f"[RAG] Low confidence ({rag_response['confidence']:.1%}), using fallback")

        # Shorter prompt
        if legal_context:
            prompt = f"""You are a legal rights assistant helping a DRIVER during a police traffic stop.

            You are advising the DRIVER, not the officer. Your job is to help the driver understand and protect their constitutional rights.    
            Scene: {scene}
            Officer: "{transcript}"
            {legal_context}
            Advice:
            Based on the legal information above, give the DRIVER brief, actionable advice in under 15 words. Help them protect their rights. Do not say anything else.
            """

        else:
            prompt = f"""You are a legal rights assistant helping a DRIVER during a police traffic stop.

            You are advising the DRIVER, not the officer. Your job is to help the driver understand and protect their constitutional rights.    
            Scene: {scene}
            Officer: "{transcript}"
            Advice:
            Based on the legal information above, give the DRIVER brief, actionable advice in under 15 words. Help them protect their rights. Do not say anything else.
            """

        # Stream response
        response = ""
        for chunk in ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            stream=True
        ):
            response += chunk["message"]["content"]
            print(chunk["message"]["content"], end="", flush=True)
        
        print()  # newline after streaming
        return response


def continuous_input_mode(client, scene_description="Pulled over, officer at window asking questions"):
    """Continuous input mode with pause detection"""
    PAUSE_THRESHOLD = 0.75

    buffer = ""
    cursor = 0
    last_input_time = time.time()
    lock = threading.Lock()
    running = True

    def timer_loop():
        nonlocal cursor, buffer
        while running:
            time.sleep(0.1)

            with lock:
                if time.time() - last_input_time >= PAUSE_THRESHOLD:
                    if cursor < len(buffer):
                        segment = buffer[cursor:].strip()
                        cursor = len(buffer)

                        if segment and segment.lower() not in ['quit', 'exit', 'q']:
                            print("\n\n" + "="*80)
                            print(f"[OFFICER SAID] {segment}")
                            print("="*80)

                            # Process through model
                            result = client.generate_advice(
                                scene=scene_description,
                                transcript=segment
                            )

                            print(f"\n[YOUR RESPONSE] {result}")
                            print("="*80 + "\n")
                            print("> ", end="", flush=True)
                        elif segment.lower() in ['quit', 'exit', 'q']:
                            print("\n\n👋 Exiting conversation mode...")
                            os._exit(0)

    def input_loop():
        nonlocal buffer, last_input_time, running

        print("\n" + "="*80)
        print("CONTINUOUS CONVERSATION MODE")
        print("Type what the officer says. Pause for 0.75s to process.")
        print("Type 'quit' and pause to exit.")
        print("="*80 + "\n")
        print("> ", end="", flush=True)

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setcbreak(fd)

            while running:
                ch = sys.stdin.read(1)

                with lock:
                    buffer += ch
                    last_input_time = time.time()

                sys.stdout.write(ch)
                sys.stdout.flush()

        except KeyboardInterrupt:
            print("\n\n👋 Exiting...")
            running = False
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # Start timer thread
    threading.Thread(target=timer_loop, daemon=True).start()
    input_loop()


if __name__ == "__main__":
    print("="*80)
    print("Nemotron Client with RAG Integration")
    print("="*80)

    # Initialize client with RAG
    client = NemotronClient(use_rag=True)

    # Initialize stop data analyzer
    rag_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rag')
    stopdata_path = os.path.join(rag_dir, 'Data', 'stopdata.csv')

    print("\n" + "-"*80)
    if os.path.exists(stopdata_path):
        analyzer = StopDataAnalyzer(stopdata_path)

        # Ask about the pullover ONCE at the start
        print("\n" + "="*80)
        pullover_input = input("Where/why were you pulled over? (e.g., 'speeding on Mission Street'): ")
        print("="*80)

        # Parse and analyze
        location, reason = analyzer.parse_pullover_input(pullover_input)

        if location:
            print(f"\n🔍 Analyzing misconduct data for {location}...")
            analysis = analyzer.analyze_location(location, radius_miles=0.25)
            summary = analyzer.generate_summary(analysis, reason)
            print(f"\n{summary}\n")
        else:
            print("\n⚠️ Could not determine location from your input. Continuing anyway...\n")
    else:
        print(f"\n⚠️ stopdata.csv not found at {stopdata_path}")
        print("Continuing without stop data analysis...\n")

    # Analyze scene from traffic stop image
    # print("\n" + "="*80)
    # image_path = "/home/dell/traffic_stop.jpg"

    # if os.path.exists(image_path):
    #     print(f"🔍 Analyzing scene from image: {image_path}")
    #     scene_analyzer = SceneAnalyzer(model="llava")
    #     scene_description = scene_analyzer.analyze(image_path)
    #     print(f"[VLM Scene Analysis] {scene_description}")
    # else:
    #     print(f"⚠️ Image not found at {image_path}, using default scene description")
    #     scene_description = "Pulled over, officer at window asking questions"

    # print("="*80)
    # trying something different by allowing any image from phone to go to this

    parser = argparse.ArgumentParser(description="Traffic stop assistant (VLM + NemoTron)")
    parser.add_argument(
        "--image-path",
        type=str,
        default=os.environ.get("TRAFFIC_STOP_IMAGE", "/home/dell/traffic_stop.jpg"),
        help="Path to a JPG/PNG image to analyze (or set TRAFFIC_STOP_IMAGE env var)."
    )
    args, _ = parser.parse_known_args()

    # Analyze scene from traffic stop image (dynamic)
    print("\n" + "="*80)
    image_path = args.image_path

    if os.path.exists(image_path):
        print(f"🔍 Analyzing scene from image: {image_path}")
        scene_analyzer = SceneAnalyzer(model="llava")
        scene_description = scene_analyzer.analyze(image_path)
        print(f"[VLM Scene Analysis] {scene_description}")
    else:
        print(f"⚠️ Image not found at {image_path}, using default scene description")
        scene_description = "Pulled over, officer at window asking questions"

    print("="*80)


    # Start continuous input mode
    continuous_input_mode(client, scene_description)
