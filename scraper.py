import re
import hashlib

from urllib.parse import urlparse, urljoin, urldefrag
from collections import defaultdict
from threading import Lock

from bs4 import BeautifulSoup

# Save ur stats
stats = {
    "uniquePages": 0,
    "longestPageUrl": "",
    "longestPageCount": 0,
    "wordFrequencies": {},
    "subdomains": {},
}
stats_lock = Lock()

# For detecting duplicates
seen_urls = set()
content_hashes = set()
seen_lock = Lock()

domain_url_count = defaultdict(int)
DOMAIN_URL_LIMIT = 500

allowed_domains = {
    ".ics.uci.edu",
    ".cs.uci.edu",
    ".informatics.uci.edu",
    ".stat.uci.edu"
}

stop_words = {
    "a","about","above","after","again","against","all","am","an","and","any",
    "are","as","at","be","because","been","before","being","below","between",
    "both","but","by","cannot","could","did","do","does","doing","down",
    "during","each","few","for","from","further","had","has","have","having",
    "he","her","here","hers","herself","him","himself","his","how","i","if",
    "in","into","is","it","its","itself","me","more","most","my","myself",
    "no","nor","not","of","off","on","once","only","or","other","ought","our",
    "ours","ourselves","out","over","own","same","she","should","so","some",
    "such","than","that","the","their","theirs","them","themselves","then",
    "there","these","they","this","those","through","to","too","under","until",
    "up","very","was","we","were","what","when","where","which","while","who",
    "whom","why","will","with","would","you","your","yours","yourself",
    "yourselves",
}

def _text_info_ratio(soup):
    return []
def _update_statistics(url, soup):
    return True

def scraper(url, resp):
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]

def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content


    if resp.status != 200 or not resp.raw_response:
        return []
    
    content = resp.raw_response.content
    if not content or len(content) < 50:
        return []
    if len(content) > 5_000_000:
        return []
    
    try:
        soup=BeautifulSoup(content, "lxml")
    except Exception:
        return []
    
    if _text_info_ratio(soup) < 0.05:
        return []
    
    text = soup.get_text(separator=" ", strip = True)
    if len(text.split()) < 20:
        return []
    
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with seen_lock:
        if text_hash in content_hashes:
            return []
        content_hashes.add(text_hash)

    defrag_url, _ = urldefrag(url)
    if not _update_statistics(defrag_url, soup):
        return []
    
    extracted = set()
    for tag in soup.find_all("a", href = True):
        href = tag["href"].strip()
        if not href or href.startswith("malito:") or href.startswith("javascript:"):
            continue
        abs_url = urljoin(resp.raw_response.url, href)
        abs_url, _ = urldefrag(abs_url)
        extracted.add(abs_url)

    return list(extracted)

def is_valid(url):
    # Decide whether to crawl this url or not. 
    # If you decide to crawl it, return True; otherwise return False.
    # There are already some conditions that return False.
    try:
        parsed = urlparse(url)
        if parsed.scheme not in set(["http", "https"]):
            return False
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz)$", parsed.path.lower())

    except TypeError:
        print ("TypeError for ", parsed)
        raise
