import os
import csv
import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import filedialog, simpledialog, Checkbutton, BooleanVar
from urllib.parse import urlparse, urljoin
import xml.etree.ElementTree as ET

class WebPageScraper:
    def __init__(self):
        self.base_url = ""
        self.folder_path = ""
        self.max_pages = 0
        self.single_file = False
        self.split_url = False
        self.create_csv = False
        self.csv_file_path = ""
        self.link_data_file_path = ""
        self.link_data = {}  # To store internal link data
        self.sitemap_urls = set()  # URLs found in the sitemap
        self.sitemap_only = {}  # Track if URLs are from sitemap only

    def set_folder_path(self, path):
        self.folder_path = path
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
    
    def save_text(self, text, url):
        filename = 'combined.txt' if self.single_file else url.replace('/', '_') + '.txt'
        file_path = os.path.join(self.folder_path, filename)
        with open(file_path, 'a', encoding='utf-8') as file:
            file.write(url + '\n\n' + text + '\n\n----------\n\n')
    
    def save_csv(self, data, file_path):
        if not os.path.exists(file_path):
            with open(file_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(data.keys())
        
        with open(file_path, 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(data.values())

    def save_link_data_csv(self):
        with open(self.link_data_file_path, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['URL', 'Inbound Links Count', 'Source URLs', 'Anchor Texts'])
            for url, data in self.link_data.items():
                writer.writerow([url, data['count'], '|'.join(data['sources']), '|'.join(data['anchors'])])
    
    def is_excluded_link(self, link):
        """Check if a link should be excluded based on its parent class hierarchy."""
        parent = link
        for _ in range(5):  # Check up to 5 levels up the DOM tree
            parent_classes = ' '.join(parent.get('class', []))
            if 'footer' in parent_classes.lower() or 'nav' in parent_classes.lower():
                return True
            parent = parent.find_parent()
            if not parent:
                break
        return False

    def parse_sitemap(self, sitemap_url):
        """Parse the sitemap.xml and store URLs."""
        try:
            response = requests.get(sitemap_url)
            response.raise_for_status()
            tree = ET.ElementTree(ET.fromstring(response.content))
            for elem in tree.iter():
                if 'loc' in elem.tag:
                    self.sitemap_urls.add(elem.text.strip())
        except requests.RequestException as e:
            print(f"Failed to retrieve or parse sitemap: {e}")

    def add_sitemap_urls(self):
        """Compare sitemap URLs with visited URLs and add missing ones."""
        new_urls = self.sitemap_urls - set(self.link_data.keys())
        for url in new_urls:
            self.sitemap_only[url] = True
            self.scrape_page(url)

    def scrape_page(self, url):
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            return

        soup = BeautifulSoup(response.content, 'html.parser')
        paragraphs = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'])
        formatted_text = '\n\n'.join(paragraph.text.strip() for paragraph in paragraphs)
        self.save_text(formatted_text, url)

        if self.create_csv:
            title = soup.title.string if soup.title else ''
            description = soup.find('meta', attrs={"name": "description"})['content'] if soup.find('meta', attrs={"name": "description"}) else ''
            h1_tags = [tag.get_text().strip() for tag in soup.find_all('h1')][:3]
            h2_tags = [tag.get_text().strip() for tag in soup.find_all('h2')][:3]

            canonical_tag = soup.find('link', rel='canonical')
            canonical_url = canonical_tag['href'] if canonical_tag else ''
            is_canonical_same = 'Yes' if canonical_url == url else 'No'

            was_sitemap_only = 'Yes' if url in self.sitemap_only else 'No'

            data = {
                'URL': url,
                'Title': title,
                'Description': description,
                'H1': '|'.join(h1_tags),
                'H2': '|'.join(h2_tags),
                'Canonical': canonical_url,
                'Is Canonical Same as URL': is_canonical_same,
                'Indexed from Sitemap': was_sitemap_only
            }
            self.save_csv(data, self.csv_file_path)

        # Process internal links for link data
        links_seen = set()
        for link in soup.find_all('a'):
            href = link.get('href')
            if href:
                next_url = urljoin(url, href)
                parsed_next_url = urlparse(next_url)
                
                # Skip self-referencing and already seen links
                if next_url == url or next_url in links_seen:
                    continue
                
                # Skip excluded links
                if self.is_excluded_link(link):
                    continue
                
                if parsed_next_url.netloc == urlparse(self.base_url).netloc:
                    if '#' in parsed_next_url.fragment:
                        continue
                    
                    # Add URL and count only if not already counted
                    if next_url not in self.link_data:
                        self.link_data[next_url] = {'count': 0, 'sources': [], 'anchors': []}
                    
                    # Track the URL and count
                    self.link_data[next_url]['count'] += 1
                    self.link_data[next_url]['sources'].append(url)
                    
                    # Only add unique anchor texts
                    anchor_text = link.get_text().strip()
                    if anchor_text not in self.link_data[next_url]['anchors']:
                        self.link_data[next_url]['anchors'].append(anchor_text)
                    
                    links_seen.add(next_url)

    def scrape_website(self):
        visited = set()
        to_visit = [self.base_url]
        scraped_urls = []
        
        while to_visit and len(visited) < self.max_pages:
            current_url = to_visit.pop(0)
            if current_url in visited or urlparse(current_url).scheme != 'https':
                continue

            # Skip URLs with a hash (#) symbol
            if '#' in urlparse(current_url).fragment:
                continue

            print(f"Scraping {current_url}")
            self.scrape_page(current_url)
            visited.add(current_url)
            scraped_urls.append(current_url)

            response = requests.get(current_url)
            soup = BeautifulSoup(response.content, 'html.parser')
            for link in soup.find_all('a'):
                href = link.get('href')
                if href:
                    next_url = urljoin(current_url, href)
                    parsed_next_url = urlparse(next_url)
                    if parsed_next_url.netloc == urlparse(self.base_url).netloc and next_url not in visited and parsed_next_url.scheme == 'https':
                        # Skip URLs with a hash (#) symbol
                        if '#' in parsed_next_url.fragment:
                            continue
                        to_visit.append(next_url)

        # Try to find and parse sitemap
        sitemap_url = urljoin(self.base_url, 'sitemap.xml')
        print(f"Looking for sitemap at {sitemap_url}")
        self.parse_sitemap(sitemap_url)

        # Add any new URLs found in the sitemap
        if self.sitemap_urls:
            self.add_sitemap_urls()

        if self.create_csv:
            self.save_link_data_csv()

if __name__ == '__main__':
    root = tk.Tk()
    root.title("Web Scraper Settings")
    
    # Variables
    base_url_var = tk.StringVar()
    max_pages_var = tk.StringVar()
    single_file_var = BooleanVar()
    split_url_var = BooleanVar()
    create_csv_var = BooleanVar()
    
    # UI Components
    tk.Label(root, text="Base URL:").grid(row=0)
    tk.Entry(root, textvariable=base_url_var).grid(row=0, column=1)
    
    tk.Label(root, text="Max Pages:").grid(row=1)
    tk.Entry(root, textvariable=max_pages_var).grid(row=1, column=1)
    
    tk.Checkbutton(root, text="Save all URLs in one file", variable=single_file_var).grid(row=2, columnspan=2)
    tk.Checkbutton(root, text="Save each URL in a separate file", variable=split_url_var).grid(row=3, columnspan=2)
    tk.Checkbutton(root, text="Create CSV with page data", variable=create_csv_var).grid(row=4, columnspan=2)
    
    def on_submit():
        scraper = WebPageScraper()
        scraper.base_url = base_url_var.get()
        scraper.max_pages = int(max_pages_var.get())
        scraper.single_file = single_file_var.get()
        scraper.split_url = split_url_var.get()
        scraper.create_csv = create_csv_var.get()
        
        folder_path = filedialog.askdirectory(mustexist=True)
        if folder_path:
            scraper.set_folder_path(folder_path)
            if scraper.create_csv:
                scraper.csv_file_path = os.path.join(folder_path, 'data.csv')
                scraper.link_data_file_path = os.path.join(folder_path, 'internal_link_data.csv')
        
        if scraper.base_url and folder_path and scraper.max_pages:
            scraper.scrape_website()
    
    tk.Button(root, text="Submit", command=on_submit).grid(row=5, columnspan=2)
    
    root.mainloop()
