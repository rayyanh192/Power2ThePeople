import pandas as pd
from collections import Counter
from transformers import pipeline
import math
import re

class StopDataAnalyzer:
    def __init__(self, csv_path: str = "stopdata.csv"):
        """Analyze historical traffic stop data"""
        print(f"Loading stop data from {csv_path}...")
        self.df = pd.read_csv(csv_path, low_memory=False)
        self._preprocess_data()
        print(f"✓ Loaded {len(self.df)} stop records")
        
    def _preprocess_data(self):
        """Clean and prepare the data"""
        print(f"Columns found: {list(self.df.columns[:5])}...")
        
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
                    # Extract coordinates from "POINT (-122.412413344 37.778045329)"
                    coords = re.findall(r'[-\d.]+', point_str)
                    if len(coords) >= 2:
                        self.df.at[idx, 'longitude'] = float(coords[0])
                        self.df.at[idx, 'latitude'] = float(coords[1])
        
        print(f"✓ Extracted coordinates for {self.df['latitude'].notna().sum()} records")
    
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance in miles between two coordinates"""
        R = 3959  # Earth's radius in miles
        
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    def get_coords_from_location(self, location_name: str):
        """
        Get coordinates from location name using free Nominatim API
        Returns (lat, lon) or None
        """
        import requests
        import time
        
        # Add "San Francisco" to improve accuracy
        search_query = f"{location_name}, San Francisco, CA"
        
        # San Francisco bounding box (viewbox parameter)
        # Southwest: 37.70, -122.52
        # Northeast: 37.83, -122.35
        
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': search_query,
            'format': 'json',
            'limit': 1,
            'viewbox': '-122.52,37.83,-122.35,37.70',  # SW lon, NE lat, NE lon, SW lat
            'bounded': 1  # Restrict results to viewbox
        }
        headers = {'User-Agent': 'TrafficStopApp/1.0'}
        
        try:
            time.sleep(1)  # Be nice to the API
            response = requests.get(url, params=params, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data:
                    lat, lon = float(data[0]['lat']), float(data[0]['lon'])
                    
                    # Double-check it's in SF (backup validation)
                    if 37.70 <= lat <= 37.83 and -122.52 <= lon <= -122.35:
                        return lat, lon
                    else:
                        print(f"⚠️ Location outside SF bounds, trying text search instead")
                        return None
        except Exception as e:
            print(f"Geocoding error: {e}")
        
        return None
    def analyze_location_by_coords(self, user_lat: float, user_lon: float, 
                                   radius_miles: float = 0.25, reason: str = None) -> dict:
        """
        Analyze patterns near specific coordinates
        
        Args:
            user_lat: User's latitude
            user_lon: User's longitude
            radius_miles: Search radius (default 0.25 miles = ~1-2 blocks)
            reason: Why they got stopped
        """
        # Filter to records with coordinates
        df_with_coords = self.df[self.df['latitude'].notna() & self.df['longitude'].notna()].copy()
        
        if len(df_with_coords) == 0:
            return {
                'found_data': False,
                'message': "No location data available for analysis."
            }
        
        # Calculate distances
        df_with_coords['distance'] = df_with_coords.apply(
            lambda row: self.haversine_distance(
                user_lat, user_lon, 
                row['latitude'], row['longitude']
            ),
            axis=1
        )
        
        # Filter to nearby incidents
        nearby = df_with_coords[df_with_coords['distance'] <= radius_miles]
        
        total_stops = len(nearby)
        
        if total_stops == 0:
            return {
                'found_data': False,
                'message': f"No incidents found within {radius_miles} miles of this location."
            }
        
        # Analyze allegations
        allegations = nearby['allegation_summary'].dropna()
        allegation_counts = Counter()
        for allegation in allegations:
            if allegation and len(str(allegation)) > 5:
                allegation_counts[str(allegation)] += 1
        
        # Analyze findings
        findings = nearby['dpa_finding'].dropna()
        finding_counts = Counter(findings)
        
        # Count sustained misconduct
        sustained_misconduct = len(nearby[
            nearby['dpa_finding'].astype(str).str.contains(
                'Sustained', case=False, na=False
            )
        ])
        
        # Count improper conduct
        improper_conduct = len(nearby[
            nearby['allegation_summary'].astype(str).str.contains(
                'improper|inappropriate|misconduct|excessive|unlawful', 
                case=False, na=False, regex=True
            )
        ])
        
        # Get closest incident for reference
        closest = nearby.nsmallest(1, 'distance').iloc[0] if len(nearby) > 0 else None
        
        return {
            'found_data': True,
            'total_stops': total_stops,
            'radius_miles': radius_miles,
            'closest_distance': closest['distance'] if closest is not None else None,
            'top_allegations': allegation_counts.most_common(3),
            'sustained_misconduct': sustained_misconduct,
            'improper_conduct': improper_conduct,
            'finding_counts': dict(finding_counts.most_common(5)),
            'user_coords': (user_lat, user_lon)
        }
    
    def analyze_location(self, user_location: str, reason: str = None, 
                        use_coords: bool = True, radius_miles: float = 0.25) -> dict:
        """
        Analyze patterns for a location - tries coordinates first, falls back to text search
        
        Args:
            user_location: Street name or area
            reason: Why they got stopped
            use_coords: Whether to try coordinate-based search
            radius_miles: Search radius for coordinate search
        """
        if use_coords:
            # Try to get coordinates for the location
            coords = self.get_coords_from_location(user_location)
            if coords:
                lat, lon = coords
                print(f"📍 Found coordinates: {lat:.6f}, {lon:.6f}")
                return self.analyze_location_by_coords(lat, lon, radius_miles, reason)
        
        # Fallback to text-based search
        print("📝 Using text-based search...")
        location_matches = self.df[
            self.df['incident_location'].astype(str).str.contains(
                user_location, case=False, na=False
            ) |
            self.df['analysis_neighborhood'].astype(str).str.contains(
                user_location, case=False, na=False
            )
        ]
        
        # Broader search if nothing found
        if len(location_matches) == 0:
            words = user_location.upper().split()
            for word in words:
                if len(word) > 3:
                    location_matches = self.df[
                        self.df['incident_location'].astype(str).str.contains(
                            word, case=False, na=False
                        ) |
                        self.df['analysis_neighborhood'].astype(str).str.contains(
                            word, case=False, na=False
                        )
                    ]
                    if len(location_matches) > 0:
                        break
        
        total_stops = len(location_matches)
        
        if total_stops == 0:
            return {
                'found_data': False,
                'message': f"No historical data found for {user_location}."
            }
        
        # Same analysis as before...
        allegations = location_matches['allegation_summary'].dropna()
        allegation_counts = Counter()
        for allegation in allegations:
            if allegation and len(str(allegation)) > 5:
                allegation_counts[str(allegation)] += 1
        
        findings = location_matches['dpa_finding'].dropna()
        finding_counts = Counter(findings)
        
        sustained_misconduct = len(location_matches[
            location_matches['dpa_finding'].astype(str).str.contains(
                'Sustained', case=False, na=False
            )
        ])
        
        improper_conduct = len(location_matches[
            location_matches['allegation_summary'].astype(str).str.contains(
                'improper|inappropriate|misconduct|excessive|unlawful', 
                case=False, na=False, regex=True
            )
        ])
        
        return {
            'found_data': True,
            'total_stops': total_stops,
            'location': user_location,
            'top_allegations': allegation_counts.most_common(3),
            'sustained_misconduct': sustained_misconduct,
            'improper_conduct': improper_conduct,
            'finding_counts': dict(finding_counts.most_common(5))
        }
    
    def generate_warning(self, analysis: dict, reason: str = None) -> str:
        """Generate summary for LLM"""
        if not analysis['found_data']:
            return analysis['message']
        
        summary_parts = []
        
        if 'radius_miles' in analysis:
            summary_parts.append(
                f"Within {analysis['radius_miles']} miles of your location:"
            )
            if analysis.get('closest_distance'):
                summary_parts.append(
                    f"Closest incident: {analysis['closest_distance']:.2f} miles away"
                )
        else:
            summary_parts.append(f"Location: {analysis.get('location', 'Unknown')}")
        
        summary_parts.append(
            f"Historical stops/complaints: {analysis['total_stops']}"
        )
        
        if analysis['sustained_misconduct'] > 0:
            summary_parts.append(
                f"⚠️ WARNING: {analysis['sustained_misconduct']} sustained misconduct findings"
            )
        
        if analysis['improper_conduct'] > 0:
            summary_parts.append(
                f"⚠️ {analysis['improper_conduct']} complaints about improper/unlawful conduct"
            )
        
        if analysis['top_allegations']:
            summary_parts.append("\nMost common allegations:")
            for allegation, count in analysis['top_allegations']:
                summary_parts.append(f"  • {allegation} ({count} cases)")
        
        if reason:
            summary_parts.append(f"\nYou were stopped for: {reason}")
        
        return "\n".join(summary_parts)


class TrafficStopAssistant:
    def __init__(self, stop_data_path: str = "stopdata.csv"):
        """Complete assistant with LLM and stop data analysis"""
        print("Loading stop data analyzer...")
        self.analyzer = StopDataAnalyzer(stop_data_path)
        
        print("Loading language model (this may take a minute)...")
        self.llm = pipeline(
            "text-generation",
            model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            max_new_tokens=100,
            device=-1
        )
        print("✓ Model loaded\n")
        
    def handle_pullover(self, location: str, reason: str = None) -> str:
        """Handle when user says they got pulled over"""
        print(f"\n🚨 Analyzing stop at: {location}")
        
        # Use coordinate-based search (0.25 miles = ~1-2 blocks)
        analysis = self.analyzer.analyze_location(location, reason, use_coords=True, radius_miles=0.25)
        data_summary = self.analyzer.generate_warning(analysis, reason)
        
        print(f"\n📊 Data found:\n{data_summary}\n")
        
        # Generate natural response with LLM
        prompt = f"""<|system|>
You are a helpful assistant. Give a brief 2-sentence warning about this traffic stop location.</|system|>

<|user|>
I got pulled over at {location}{f' for {reason}' if reason else ''}. 

Data:
{data_summary}

What should I know?</|user|>

<|assistant|>"""
        
        response = self.llm(prompt, do_sample=True)[0]['generated_text']
        assistant_response = response.split("<|assistant|>")[-1].strip()
        assistant_response = assistant_response.split("<|")[0].strip()
        
        return assistant_response
    
    def parse_voice_input(self, text: str) -> tuple:
        """Extract location and reason from voice input"""
        location = None
        reason = None
        
        if " at " in text.lower():
            location = text.lower().split(" at ")[1].split(" for ")[0].strip()
        elif " on " in text.lower():
            location = text.lower().split(" on ")[1].split(" for ")[0].strip()
        
        if " for " in text.lower():
            reason = text.lower().split(" for ")[1].strip()
        
        return location, reason
    
    def process_input(self, text: str) -> str:
        """Main entry point"""
        location, reason = self.parse_voice_input(text)
        
        if not location:
            return "I didn't catch where you got pulled over. Can you say the street or area?"
        
        return self.handle_pullover(location, reason)


# TESTING
if __name__ == "__main__":
    assistant = TrafficStopAssistant("stopdata.csv")
    
    print("="*80)
    print("TRAFFIC STOP ASSISTANT - TESTING")
    print("="*80 + "\n")
    
    # Test cases
    tests = [
        "I just got pulled over at Mission Street for speeding",
        "Got stopped on Market and 5th",
    ]
    
    for test in tests:
        print(f"👤 USER: {test}")
        response = assistant.process_input(test)
        print(f"🤖 ASSISTANT: {response}")
        print("\n" + "="*80 + "\n")
    
    # Interactive mode
    print("\n💬 Try your own! Type 'quit' to exit\n")
    while True:
        user_input = input("What happened? > ").strip()
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("👋 Goodbye!")
            break
        if user_input:
            response = assistant.process_input(user_input)
            print(f"\n🤖 {response}\n")