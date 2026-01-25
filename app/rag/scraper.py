import requests
from bs4 import BeautifulSoup
import json
import time
from urllib.parse import urljoin, urlparse
import re
from typing import List, Dict
import pandas as pd
import os

class TrafficRightsScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.scraped_data = []

    def clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def extract_structured_content(self, soup: BeautifulSoup, url: str) -> Dict:
        content = {'url': url, 'title': '', 'sections': [], 'key_rights': [], 'scenarios': []}

        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            content['title'] = self.clean_text(title_tag.get_text())

        main_content = (
            soup.find('main') or 
            soup.find('article') or 
            soup.find('div', class_=re.compile('content|article|post', re.I)) or
            soup.find('body')
        )

        if main_content:
            headers = main_content.find_all(['h2', 'h3', 'h4'])
            for header in headers:
                section_title = self.clean_text(header.get_text())
                section_content = []
                for sibling in header.find_next_siblings():
                    if sibling.name in ['h2', 'h3', 'h4']:
                        break
                    if sibling.name in ['p', 'ul', 'ol', 'li']:
                        text = self.clean_text(sibling.get_text())
                        if text:
                            section_content.append(text)
                if section_content:
                    content['sections'].append({'heading': section_title, 'content': ' '.join(section_content)})

            lists = main_content.find_all(['ul', 'ol'])
            for lst in lists:
                items = lst.find_all('li')
                for item in items:
                    text = self.clean_text(item.get_text())
                    if any(keyword in text.lower() for keyword in [
                        'right to', 'can refuse', 'must', 'required', 'not required', 
                        'officer must', 'you may', 'you can', 'allowed to', 'permitted',
                        'prohibited', 'illegal', 'legal', 'lawful', 'unlawful',
                        'constitutional', 'amendment', 'warrant', 'consent',
                        'refuse to', 'decline', 'ask for', 'request', 'demand',
                        'stop and frisk', 'terry stop', 'reasonable suspicion',
                        'probable cause', 'arrest', 'detention', 'custody',
                        'miranda', 'lawyer', 'attorney', 'remain silent',
                        'search warrant', 'seizure', 'evidence', 'suppress',
                        'traffic stop', 'pulled over', 'vehicle code', 'violation',
                        'license and registration', 'identification', 'id',
                        'breathalyzer', 'sobriety test', 'field test', 'blood test',
                        'passenger', 'driver', 'occupant', 'vehicle',
                        'recording', 'film', 'video', 'photograph', 'dashcam',
                        'complaint', 'file report', 'badge number', 'officer name',
                        'civil rights', 'discrimination', 'racial profiling',
                        'excessive force', 'police brutality', 'misconduct'
                    ]):
                        content['key_rights'].append(text)
        return content

    def process_laws_txt(self, filepath: str = '/home/dell/Power2ThePeople/app/rag/Data/laws.txt'): 
        """Process the laws.txt file and extract structured content"""
        print("\n" + "="*60)
        print("PROCESSING LAWS.TXT FILE")
        print("="*60)
        
        if not os.path.exists(filepath):
            print(f"❌ laws.txt not found at {filepath}")
            return
        
        with open(filepath, 'r', encoding='utf-8') as f:
            laws_content = f.read()
        
        # Split content into sections based on common patterns
        # Looking for section headers like "SECTION 12345" or "Article X"
        section_pattern = r'(SECTION\s+\d+|Article\s+\w+|Chapter\s+\w+|§\s*\d+)'
        sections = re.split(section_pattern, laws_content)
        
        print(f"📄 Found {len(sections)//2} sections in laws.txt")
        
        # Process sections
        for i in range(1, len(sections), 2):
            if i+1 < len(sections):
                section_header = sections[i].strip()
                section_content = sections[i+1].strip()
                
                if section_content:  # Only add if there's actual content
                    self.scraped_data.append({
                        'url': '/home/dell/Power2ThePeople/app/rag/Data/laws.txt',
                        'title': 'California Vehicle Code',
                        'sections': [{
                            'heading': section_header,
                            'content': section_content
                        }],
                        'key_rights': [],
                        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
        
        print(f"✅ Processed laws.txt - added {len(sections)//2} sections")

    def scrape_url(self, url: str) -> Dict:
        print(f"Scraping: {url}")
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                script.decompose()
            content = self.extract_structured_content(soup, url)
            content['scraped_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            return content
        except Exception as e:
            print(f"Error scraping {url}: {str(e)}")
            return {'url': url, 'error': str(e)}

    def scrape_urls(self, urls: List[str], delay: float = 2.0) -> List[Dict]:
        results = []
        for i, url in enumerate(urls):
            print(f"\nProcessing {i+1}/{len(urls)}")
            result = self.scrape_url(url)
            results.append(result)
            self.scraped_data.append(result)
            if i < len(urls) - 1:
                time.sleep(delay)
        return results

    def extract_scenarios(self, data: List[Dict]) -> List[Dict]:
        scenarios = []
        scenario_keywords = {
            'vehicle_search': ['search', 'search vehicle', 'consent to search', 'trunk search', 'glove box', 'compartment'],
            'refuse_questions': ['remain silent', 'refuse to answer', 'fifth amendment', 'right to silence', 'miranda'],
            'exit_vehicle': ['exit vehicle', 'step out', 'get out of car', 'leave vehicle', 'order out'],
            'dui_test': ['breathalyzer', 'field sobriety', 'chemical test', 'blood test', 'preliminary alcohol', 'pas test'],
            'recording': ['record', 'film', 'video', 'photograph', 'camera', 'dashcam', 'body cam'],
            'identification': ['show id', 'identification', 'driver license', 'name and address', 'identify yourself'],
            'passengers': ['passenger rights', 'passenger', 'occupant', 'backseat'],
            'probable_cause': ['probable cause', 'reasonable suspicion', 'articulable facts', 'terry stop'],
            'speeding': ['speed limit', 'speeding', 'mph', 'radar', 'excessive speed', 'lidar', 'pacing'],
            'stop_sign': ['stop sign', 'rolling stop', 'complete stop', 'failure to stop', 'california stop'],
            'red_light': ['red light', 'traffic signal', 'ran a red', 'signal violation', 'yellow light'],
            'lane_change': ['lane change', 'unsafe lane', 'improper lane', 'turn signal', 'merge', 'weaving'],
            'right_of_way': ['right of way', 'yield', 'pedestrian', 'crosswalk', 'intersection'],
            'following_distance': ['following too close', 'tailgating', 'safe distance', 'following distance'],
            'headlights': ['headlights', 'high beams', 'lights required', 'illumination', 'tail lights', 'brake lights'],
            'seatbelt': ['seatbelt', 'seat belt', 'safety restraint', 'child seat', 'booster'],
            'cell_phone': ['cell phone', 'mobile phone', 'texting', 'handheld device', 'distracted driving'],
            'parking': ['parking', 'parked', 'no parking', 'illegal parking', 'parking ticket', 'meter'],
            'dui': ['dui', 'driving under influence', 'intoxicated', 'impaired', 'drunk driving', 'dwi'],
            'reckless_driving': ['reckless', 'careless', 'dangerous driving', 'street racing', 'exhibition of speed'],
            'license_registration': ['license', 'registration', 'proof of insurance', 'expired', 'suspended'],
            'warrant': ['warrant', 'arrest warrant', 'bench warrant', 'outstanding warrant'],
            'miranda_rights': ['miranda', 'right to attorney', 'right to remain silent', 'anything you say'],
            'pretextual_stop': ['pretextual', 'pretext stop', 'racial profiling', 'discriminatory'],
            'checkpoint': ['checkpoint', 'dui checkpoint', 'sobriety checkpoint', 'roadblock'],
            'k9_search': ['drug dog', 'k9', 'canine', 'dog sniff', 'drug sniff'],
            'traffic_ticket': ['citation', 'ticket', 'infraction', 'fine', 'court date', 'traffic court'],
            'towing': ['tow', 'impound', 'vehicle impound', 'towing fees'],
            'arrest': ['arrest', 'handcuffs', 'custody', 'detained', 'booking'],
            'use_of_force': ['use of force', 'excessive force', 'police brutality', 'taser', 'pepper spray'],
            'complaint': ['complaint', 'file complaint', 'police misconduct', 'internal affairs'],
        }

        for item in data:
            if 'sections' in item:
                for section in item['sections']:
                    heading = section['heading'].lower()
                    content = section['content'].lower()
                    for scenario_type, keywords in scenario_keywords.items():
                        if any(keyword in heading or keyword in content for keyword in keywords):
                            scenarios.append({
                                'scenario_type': scenario_type,
                                'heading': section['heading'],
                                'content': section['content'],
                                'source_url': item['url']
                            })
        return scenarios

    def save_to_json(self, filename: str):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.scraped_data, f, indent=2, ensure_ascii=False)
        print(f"Data saved to {filename}")

    def save_to_csv(self, filename: str):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        rows = []
        for item in self.scraped_data:
            for section in item.get('sections', []):
                rows.append({'url': item['url'], 'title': item.get('title', ''), 'section_heading': section['heading'], 'content': section['content']})
            for right in item.get('key_rights', []):
                rows.append({'url': item['url'], 'title': item.get('title', ''), 'section_heading': 'Key Right', 'content': right})
        df = pd.DataFrame(rows)
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"Data saved to {filename}")

    def create_training_dataset(self, filename: str):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        scenarios = self.extract_scenarios(self.scraped_data)
        training_examples = []
        for scenario in scenarios:
            training_examples.append({
                'prompt': f"What are my rights regarding {scenario['scenario_type'].replace('_',' ')} during a California traffic stop?",
                'completion': scenario['content'],
                'metadata': {'scenario_type': scenario['scenario_type'], 'source': scenario['source_url']}
            })
        with open(filename, 'w', encoding='utf-8') as f:
            for ex in training_examples:
                f.write(json.dumps(ex, ensure_ascii=False) + '\n')
        print(f"Training dataset saved to {filename} ({len(training_examples)} examples)")

# Main execution
if __name__ == "__main__":
    urls = [
    'https://leginfo.legislature.ca.gov/faces/codes_displayexpandedbranch.xhtml?tocCode=VEH&division=11.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=40302.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=40508.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=23612.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=2806.5.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=22350.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=26708.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=22651.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=12951.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=27315.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=2814.2.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=12500.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=14601.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=16028.',

    # Penal Code (reasonable suspicion, search warrant procedure, etc.)
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=PEN&sectionNum=836.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=PEN&sectionNum=834.',
    'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=PEN&sectionNum=148.',

    # Miranda / Custodial interrogation area
    # (traffic stops typically do NOT require Miranda until custodial interrogation)
    'https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=PEN&division=&title=1.&part=2.&chapter=5.&article=3.',

    # --- U.S. SUPREME COURT & KEY CONSTITUTIONAL CASES ---
    # Fourth Amendment (searches & seizures) and traffic stop precedent
    'https://supreme.justia.com/cases/federal/us/575/348/',
    'https://supreme.justia.com/cases/federal/us/434/106/',
    'https://supreme.justia.com/cases/federal/us/468/420/',  # *Berkemer v. McCarty* – traffic stops & Miranda
    'https://supreme.justia.com/cases/federal/us/519/408/',
    'https://supreme.justia.com/cases/federal/us/573/373/',
    'https://supreme.justia.com/cases/federal/us/517/806/',
    'https://supreme.justia.com/cases/federal/us/542/177/',
    'https://supreme.justia.com/cases/federal/us/434/429/',
    'https://supreme.justia.com/cases/federal/us/553/164/',
    'https://supreme.justia.com/cases/federal/us/566/426/',
    'https://supreme.justia.com/cases/federal/us/384/436/',
    'https://supreme.justia.com/cases/federal/us/512/477/',
    'https://supreme.justia.com/cases/federal/us/469/221/',
    'https://supreme.justia.com/cases/federal/us/525/83/',
    'https://supreme.justia.com/cases/federal/us/412/218/',
    'https://supreme.justia.com/cases/federal/us/555/323/',
    'https://supreme.justia.com/cases/federal/us/496/444/',
    'https://supreme.justia.com/cases/federal/us/543/405/',
    'https://supreme.justia.com/cases/federal/us/569/1/',
    'https://supreme.justia.com/cases/federal/us/575/348/',

    # Ninth Circuit / regional (civil rights and searches)
    'https://www.ca9.uscourts.gov/opinions/view_subpage.php?pk_id=0000016937',
    'https://caselaw.findlaw.com/court/us-9th-circuit/1068653.html',

    # --- ACLU & CIVIL LIBERTIES GROUPS (Know Your Rights) ---
    'https://www.aclu.org/know-your-rights/stopped-by-police',
    'https://www.aclunorcal.org/our-work/know-your-rights/know-your-rights-police-interactions',  # ACLU interactive page w/ details :contentReference[oaicite:0]{index=0}
    'https://www.aclunc.org/sites/default/files/ENGLISH%20KYR%20Police%20Interactions%20English%20printable%202%20pages%20October%202025.pdf',  # Printable ACLU guide :contentReference[oaicite:1]{index=1}
    'https://www.aclunc.org/sites/default/files/KYR%20Unhoused%20-%20ENGLISH%20-%20March%202025_1m.pdf',  # More extended ACLU KYR :contentReference[oaicite:2]{index=2}

    # --- STATE & LOCAL RESOURCES ---
    'https://oag.ca.gov/system/files/media/lapd-consent-search-advisement-2020.pdf',
    'https://oag.ca.gov/system/files/media/2024-draft-ripa-report.pdf',
    'https://www.dmv.ca.gov/portal/handbook/california-driver-handbook/laws-and-rules-of-the-road/',
    'https://www.dmv.ca.gov/portal/handbook/california-driver-handbook/safe-driving/',
    'https://www.dmv.ca.gov/portal/handbook/california-driver-handbook/alcohol-and-drugs/',
    'https://www.dmv.ca.gov/portal/handbook/california-driver-handbook/navigating-the-roads/',
    'https://www.chp.ca.gov/notify-chp/',
    'https://www.sf.gov/sites/default/files/2023-01/PoliceCommission11123-DGO%209.07_12.28.22_CLEAN.pdf',  # SF policy :contentReference[oaicite:3]{index=3}
    'https://www.sf.gov/sites/default/files/2022-10/Police%20Commission%201122022-Lofstrom_SF%20Police%20Commission_Nov%202%202022.pdf',

    # --- PRACTICAL LEGAL GUIDES & OVERVIEWS ---
    'https://legalclarity.org/your-rights-under-california-traffic-stop-laws/',
    'https://legalclarity.org/what-are-my-rights-during-a-traffic-stop-in-california/',
    'https://legalclarity.org/search-and-seizure-laws-in-california/',
    'https://www.findlaw.com/legalblogs/criminal-defense/civil-rights-during-a-traffic-stop-5-reminders/',  # General civil rights on stops :contentReference[oaicite:4]{index=4}
    'https://www.superlawyers.com/resources/civil-rights/california/what-rights-do-you-have-during-a-traffic-stop-in-california/',  # High‑level rights overview :contentReference[oaicite:5]{index=5}
    'https://gabrielaguraiiblaw.com/your-rights-california-traffic-stop/',  # Practical rights explanation :contentReference[oaicite:6]{index=6}

    # --- ADDITIONAL/GENERAL LEGAL INFO RESOURCES ---
    'https://www.nolo.com/legal-encyclopedia/what-do-during-traffic-stop-california.html',
    'https://www.avvo.com/legal-guides/ugc/know-your-rights-during-a-traffic-stop-in-california',
    'https://www.criminaldefenselawyer.com/resources/traffic-tickets/traffic-stop.htm',
    'https://www.lawyers.com/legal-info/criminal/dui-dwi/traffic-stop-rights.html',
]


    scraper = TrafficRightsScraper()
    
    # FIRST: Process laws.txt
    print("="*60)
    print("STEP 1: Processing laws.txt")
    print("="*60)
    scraper.process_laws_txt('/home/dell/Power2ThePeople/app/rag/Data/laws.txt')
    
    # SECOND: Scrape all URLs
    print("\n" + "="*60)
    print("STEP 2: Web scraping URLs")
    print("="*60)
    print(f"Total URLs to scrape: {len(urls)}")
    results = scraper.scrape_urls(urls, delay=2.0)
    
    # Save results
    print("\n" + "="*60)
    print("STEP 3: Saving results")
    print("="*60)
    scraper.save_to_json('/home/dell/Power2ThePeople/app/rag/Data/traffic_rights_raw.json')
    scraper.save_to_csv('/home/dell/Power2ThePeople/app/rag/Data/traffic_rights_structured.csv')
    scraper.create_training_dataset('/home/dell/Power2ThePeople/app/rag/Data/traffic_rights_training.jsonl')

    # Summary
    print("\n" + "="*60)
    print("SCRAPING SUMMARY")
    print("="*60)
    print(f"Total sources processed: {len(scraper.scraped_data)}")
    print(f"  - laws.txt sections: ~{len([x for x in scraper.scraped_data if x['url'] == '/home/dell/Power2ThePeople/app/rag/Data/laws.txt'])}")
    print(f"  - Web URLs scraped: {len(results)}")
    total_sections = sum(len(item.get('sections', [])) for item in scraper.scraped_data)
    total_rights = sum(len(item.get('key_rights', [])) for item in scraper.scraped_data)
    print(f"Total sections extracted: {total_sections}")
    print(f"Total key rights identified: {total_rights}")
    print("\nDone!")