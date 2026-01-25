import requests
from bs4 import BeautifulSoup
import json
import time
from urllib.parse import urljoin, urlparse
import re
from typing import List, Dict
import pandas as pd

class TrafficRightsScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.scraped_data = []
        
    def clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters but keep punctuation
        text = text.strip()
        return text
    
    def extract_structured_content(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extract structured content from a page"""
        content = {
            'url': url,
            'title': '',
            'sections': [],
            'key_rights': [],
            'scenarios': []
        }
        
        # Get title
        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            content['title'] = self.clean_text(title_tag.get_text())
        
        # Extract main content - looking for common content containers
        main_content = (
            soup.find('main') or 
            soup.find('article') or 
            soup.find('div', class_=re.compile('content|article|post', re.I)) or
            soup.find('body')
        )
        
        if main_content:
            # Extract sections with headers
            headers = main_content.find_all(['h2', 'h3', 'h4'])
            for header in headers:
                section_title = self.clean_text(header.get_text())
                
                # Get content until next header
                section_content = []
                for sibling in header.find_next_siblings():
                    if sibling.name in ['h2', 'h3', 'h4']:
                        break
                    if sibling.name in ['p', 'ul', 'ol', 'li']:
                        text = self.clean_text(sibling.get_text())
                        if text:
                            section_content.append(text)
                
                if section_content:
                    content['sections'].append({
                        'heading': section_title,
                        'content': ' '.join(section_content)
                    })
            
            # Extract bullet points/lists that often contain rights
            lists = main_content.find_all(['ul', 'ol'])
            for lst in lists:
                items = lst.find_all('li')
                for item in items:
                    text = self.clean_text(item.get_text())
                    # Look for rights-related keywords
                    if any(keyword in text.lower() for keyword in [
                        'right to', 'can refuse', 'must', 'required', 
                        'not required', 'officer must', 'you may', 'you can'
                    ]):
                        content['key_rights'].append(text)
        
        return content
    
    def crawl_justia_vehicle_code(self, start_url: str) -> List[str]:
        """
        Crawl Justia California Vehicle Code to find all section URLs
        
        Args:
            start_url: Starting URL (e.g., division-11 page)
        
        Returns:
            List of all section URLs found
        """
        print(f"\n🕷️  CRAWLING Justia Vehicle Code from: {start_url}")
        all_urls = []
        
        try:
            response = requests.get(start_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all links on the page
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link['href']
                
                # Convert relative URLs to absolute
                if href.startswith('/'):
                    href = f"https://law.justia.com{href}"
                
                # Only include California Vehicle Code links
                if 'california/code-veh' in href and href not in all_urls:
                    # Filter for actual content pages (sections, articles, chapters)
                    if any(x in href for x in ['section-', 'article-', 'chapter-']):
                        all_urls.append(href)
                        print(f"  Found: {href}")
            
            print(f"✅ Found {len(all_urls)} California Vehicle Code URLs")
            
        except Exception as e:
            print(f"❌ Error crawling {start_url}: {str(e)}")
        
        return all_urls
    
    def scrape_url(self, url: str) -> Dict:
        """Scrape a single URL"""
        print(f"Scraping: {url}")
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                script.decompose()
            
            content = self.extract_structured_content(soup, url)
            
            # Add timestamp
            content['scraped_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            return content
            
        except Exception as e:
            print(f"Error scraping {url}: {str(e)}")
            return {'url': url, 'error': str(e)}
    
    def scrape_urls(self, urls: List[str], delay: float = 2.0) -> List[Dict]:
        """Scrape multiple URLs with delay between requests"""
        results = []
        
        for i, url in enumerate(urls):
            print(f"\nProcessing {i+1}/{len(urls)}")
            result = self.scrape_url(url)
            results.append(result)
            self.scraped_data.append(result)
            
            # Be respectful - add delay between requests
            if i < len(urls) - 1:
                time.sleep(delay)
        
        return results
    
    def extract_scenarios(self, data: List[Dict]) -> List[Dict]:
        """Extract specific scenarios and rights from scraped data"""
        scenarios = []
        
        scenario_keywords = {
            # Rights-based scenarios
            'vehicle_search': ['search', 'search vehicle', 'consent to search'],
            'refuse_questions': ['remain silent', 'refuse to answer', 'fifth amendment'],
            'exit_vehicle': ['exit vehicle', 'step out', 'get out of car'],
            'dui_test': ['breathalyzer', 'field sobriety', 'chemical test', 'blood test'],
            'recording': ['record', 'film', 'video', 'photograph'],
            'identification': ['show id', 'identification', 'driver license'],
            'passengers': ['passenger rights', 'passenger'],
            'probable_cause': ['probable cause', 'reasonable suspicion'],
            
            # Traffic law scenarios (NEW - for understanding WHY they were pulled over)
            'speeding': ['speed limit', 'speeding', 'mph', 'radar', 'excessive speed'],
            'stop_sign': ['stop sign', 'rolling stop', 'complete stop', 'failure to stop'],
            'red_light': ['red light', 'traffic signal', 'ran a red', 'signal violation'],
            'lane_change': ['lane change', 'unsafe lane', 'improper lane', 'turn signal'],
            'right_of_way': ['right of way', 'yield', 'pedestrian', 'crosswalk'],
            'following_distance': ['following too close', 'tailgating', 'safe distance'],
            'headlights': ['headlights', 'high beams', 'lights required', 'illumination'],
            'seatbelt': ['seatbelt', 'seat belt', 'safety restraint'],
            'cell_phone': ['cell phone', 'mobile phone', 'texting', 'handheld device'],
            'parking': ['parking', 'parked', 'no parking', 'illegal parking'],
            'dui': ['dui', 'driving under influence', 'intoxicated', 'impaired'],
            'reckless_driving': ['reckless', 'careless', 'dangerous driving'],
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
    
    def save_to_json(self, filename: str = 'data/traffic_rights_data.json'):
        """Save scraped data to JSON"""
        import os
        os.makedirs('data', exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.scraped_data, f, indent=2, ensure_ascii=False)
        print(f"\nData saved to {filename}")
    
    def save_to_csv(self, filename: str = 'data/traffic_rights_data.csv'):
        """Save scraped data to CSV format for easier training"""
        import os
        os.makedirs('data', exist_ok=True)
        
        rows = []
        
        for item in self.scraped_data:
            if 'sections' in item:
                for section in item['sections']:
                    rows.append({
                        'url': item['url'],
                        'title': item.get('title', ''),
                        'section_heading': section['heading'],
                        'content': section['content']
                    })
            
            if 'key_rights' in item:
                for right in item['key_rights']:
                    rows.append({
                        'url': item['url'],
                        'title': item.get('title', ''),
                        'section_heading': 'Key Right',
                        'content': right
                    })
        
        df = pd.DataFrame(rows)
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"Data saved to {filename}")
    
    def create_training_dataset(self, filename: str = 'data/training_data.jsonl'):
        """Create a JSONL file formatted for model training"""
        import os
        os.makedirs('data', exist_ok=True)
        
        scenarios = self.extract_scenarios(self.scraped_data)
        
        training_examples = []
        
        for scenario in scenarios:
            # Create prompt-completion pairs
            example = {
                'prompt': f"What are my rights regarding {scenario['scenario_type'].replace('_', ' ')} during a California traffic stop?",
                'completion': scenario['content'],
                'metadata': {
                    'scenario_type': scenario['scenario_type'],
                    'source': scenario['source_url']
                }
            }
            training_examples.append(example)
        
        # Save as JSONL
        with open(filename, 'w', encoding='utf-8') as f:
            for example in training_examples:
                f.write(json.dumps(example, ensure_ascii=False) + '\n')
        
        print(f"Training dataset saved to {filename} ({len(training_examples)} examples)")


# Main execution
if __name__ == "__main__":
    # URLs to scrape - RIGHTS + TRAFFIC LAWS
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
        'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=PEN&sectionNum=836.',
        'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=PEN&sectionNum=1538.5.',
        
        'https://supreme.justia.com/cases/federal/us/575/348/',
        'https://supreme.justia.com/cases/federal/us/434/106/',
        'https://supreme.justia.com/cases/federal/us/519/408/',
        'https://supreme.justia.com/cases/federal/us/573/373/',
        'https://supreme.justia.com/cases/federal/us/517/806/',
        'https://supreme.justia.com/cases/federal/us/542/177/',
        'https://supreme.justia.com/cases/federal/us/434/429/',
        'https://supreme.justia.com/cases/federal/us/267/132/',
        
        'https://www.aclu.org/know-your-rights/stopped-by-police',
        'https://www.aclunorcal.org/know-your-rights/police-interactions/',
        'https://www.aclunorcal.org/sites/default/files/kyr_police_en.pdf',
        'https://www.aclusocal.org/know-your-rights/when-stopped-officer/',
        'https://www.aclusocal.org/app/uploads/2016/12/know_your_rights_what_to_do_if_questioned_by_police_fbi.pdf',
        'https://www.aclu.org/sites/default/files/field_document/bustcard_eng_20100630.pdf',
        'https://aclucalaction.org/wp-content/uploads/2023/03/AB-93-Fact-Sheet.pdf',
        
        'https://oag.ca.gov/system/files/media/lapd-consent-search-advisement-2020.pdf',
        'https://oag.ca.gov/system/files/media/2024-draft-ripa-report.pdf',
        
        'https://www.dmv.ca.gov/portal/handbook/california-driver-handbook/laws-and-rules-of-the-road/',
        'https://www.dmv.ca.gov/portal/handbook/california-driver-handbook/safe-driving/',
        'https://www.dmv.ca.gov/portal/handbook/california-driver-handbook/alcohol-and-drugs/',
        'https://www.dmv.ca.gov/portal/handbook/california-driver-handbook/navigating-the-roads/',
        
        'https://www.chp.ca.gov/notify-chp/',
        
        'https://www.sf.gov/sites/default/files/2023-01/PoliceCommission11123-DGO%209.07_12.28.22_CLEAN.pdf',
        'https://www.sf.gov/sites/default/files/2022-10/Police%20Commission%201122022-Lofstrom_SF%20Police%20Commission_Nov%202%202022.pdf',
        'https://www.sanfranciscopolice.org/your-sfpd/policies/bias-free-policing',
        'https://www.sfmta.com/getting-around/drive-park/how-avoid-parking-tickets',
        
        'https://le.alcoda.org/publications/point_of_view/files/traffic_stops.pdf',
        'https://le.alcoda.org/publications/point_of_view/files/SS15_CONSENT_SEARCHES.pdf',
        
        'https://www.uscourts.gov/about-federal-courts/educational-resources/educational-activities/fourth-amendment-activities/brendlin-',
        
        'https://www.courts.ca.gov/selfhelp-traffic.htm',
        'https://santaclara.courts.ca.gov/system/files/general/resource-materials-specific-infractions.pdf',
        
        'https://law.stanford.edu/2023/05/10/pretext-stops-in-san-francisco-will-reforms-reduce-violence-and-injustice/',
        
        'https://epic.org/federal-court-rules-police-may-not-compel-passenger-id-during-traffic-stop/',
        'https://epic.org/documents/riley-v-california-2/',
        
        'https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=PEN&division=&title=1.&part=2.&chapter=5.&article=3.',  # Search warrants
        
        'https://law.justia.com/codes/california/2023/code-veh/division-11/',
        'https://law.justia.com/codes/california/code-veh/division-6/chapter-4/section-14602-6/',
        'https://codes.findlaw.com/ca/vehicle-code/',
        
        'https://legalclarity.org/your-rights-under-california-traffic-stop-laws/',
        'https://legalclarity.org/what-are-my-rights-during-a-traffic-stop-in-california/',
        'https://legalclarity.org/search-and-seizure-laws-in-california/',
        
        'https://supreme.justia.com/cases/federal/us/462/213/',
        'https://supreme.justia.com/cases/federal/us/460/730/',
        'https://supreme.justia.com/cases/federal/us/496/325/',
        'https://supreme.justia.com/cases/federal/us/553/164/',
        'https://supreme.justia.com/cases/federal/us/566/426/',
        
        'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=PEN&sectionNum=834.',
        'https://supreme.justia.com/cases/federal/us/384/436/',
        'https://supreme.justia.com/cases/federal/us/512/477/',
        
        'https://supreme.justia.com/cases/federal/us/469/221/',
        'https://supreme.justia.com/cases/federal/us/525/83/',
        
        'https://supreme.justia.com/cases/federal/us/412/218/',
        
        'https://supreme.justia.com/cases/federal/us/555/323/',
        
        'https://www.ca9.uscourts.gov/opinions/view_subpage.php?pk_id=0000016937',
        
        'https://supreme.justia.com/cases/federal/us/479/367/',
        
        'https://supreme.justia.com/cases/federal/us/496/444/',
        'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=2814.2.',
        
        'https://supreme.justia.com/cases/federal/us/543/405/',
        'https://supreme.justia.com/cases/federal/us/569/1/',
        
        'https://caselaw.findlaw.com/court/us-9th-circuit/1068653.html',
    ]



    
    # Initialize scraper
    scraper = TrafficRightsScraper()
    
    # Scrape all URLs
    print("Starting web scraping...")
    print("=" * 60)
    results = scraper.scrape_urls(urls, delay=2.0)
    
    # Save results in multiple formats
    print("\n" + "=" * 60)
    print("Saving results...")
    scraper.save_to_json('data/traffic_rights_raw.json')
    scraper.save_to_csv('data/traffic_rights_structured.csv')
    scraper.create_training_dataset('data/traffic_rights_training.jsonl')
    
    # Print summary
    print("\n" + "=" * 60)
    print("SCRAPING SUMMARY")
    print("=" * 60)
    print(f"Total URLs scraped: {len(results)}")
    
    total_sections = sum(len(item.get('sections', [])) for item in results)
    total_rights = sum(len(item.get('key_rights', [])) for item in results)
    
    print(f"Total sections extracted: {total_sections}")
    print(f"Total key rights identified: {total_rights}")
    
    print("\nFiles created in 'data' folder:")
    print("  - data/traffic_rights_raw.json (full scraped data)")
    print("  - data/traffic_rights_structured.csv (tabular format)")
    print("  - data/traffic_rights_training.jsonl (model training format)")
    print("\nDone!")