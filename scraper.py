import re
import atexit
import hashlib
import collections
from urllib.parse import urlparse, urljoin, urldefrag

from bs4 import BeautifulSoup

UNIQUE_URLS = set()
CONTENT_HASHES = set()
WORD_COUNTS = collections.Counter()
LONGEST = {"url": None, "count": 0}
SUBDOMAIN_COUNTS = collections.defaultdict(set)
_PAGES_SINCE_DUMP = 0

STOPWORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can't",
    "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't",
    "doing", "don't", "down", "during", "each", "few", "for", "from",
    "further", "get", "got", "had", "hadn't", "has", "hasn't", "have",
    "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't",
    "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't",
    "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only",
    "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
    "same", "shan't", "she", "she'd", "she'll", "she's", "should",
    "shouldn't", "so", "some", "such", "than", "that", "that's", "the",
    "their", "theirs", "them", "themselves", "then", "there", "there's",
    "these", "they", "they'd", "they'll", "they're", "they've", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't",
    "what", "what's", "when", "when's", "where", "where's", "which", "while",
    "who", "who's", "whom", "why", "why's", "will", "with", "won't",
    "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've",
    "your", "yours", "yourself", "yourselves",
})

_ALLOWED_DOMAINS = (
    ".ics.uci.edu",
    ".cs.uci.edu",
    ".informatics.uci.edu",
    ".stat.uci.edu",
)

_EXT_RE = re.compile(
    r".*\.(css|js|bmp|gif|jpe?g|ico|png|tiff?|mid|mp2|mp3|mp4"
    r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
    r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
    r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
    r"|epub|dll|cnf|tgz|sha1|thmx|mso|arff|rtf|jar|csv"
    r"|rm|smil|wmv|swf|wma|zip|rar|gz"
    r"|apk|war|class|woff2?|ttf|eot|svg|json|xml|sql|sqlite|db"
    r"|bib|odp|ods|odt|nb|mat|fig|m)$",
    re.IGNORECASE,
)

_DATE_RE = re.compile(r"\d{4}[-/]\d{1,2}([-/]\d{1,2})?")

_TRAP_PARAMS = frozenset({
    "action", "replytocom", "redirect_to", "share", "format",
    "do", "sectok", "rev", "idx", "sort", "order", "filter",
    "search", "s", "q", "query", "keywords", "tag", "category",
    "lang", "locale", "ical", "token", "session", "sid",
    "sessionid", "phpsessid", "jsessionid", "cfid", "cftoken",
    "login", "auth", "sso", "oauth", "signup", "signin",
    "register", "redirect", "return", "next", "ref", "referrer",
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "fbclid", "gclid", "msclkid",
})

_VCS_SEGMENTS = frozenset({
    "commit", "commits", "tree", "blob", "blame",
    "diff", "compare", "raw", "history", "branches",
})

_AUTH_RE = re.compile(
    r"/(login|logout|signup|sign-?in|register|auth|sso|oauth)/?"
    r"|[?&](login|logout|signup|signin|auth|sso|oauth)=",
    re.IGNORECASE,
)

_CALENDAR_RE = re.compile(
    r"/(calendar|events?|ical|eventdate|tribe-bar-date)/",
    re.IGNORECASE,
)


def scraper(url, resp):
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]


def extract_next_links(url, resp):
    global _PAGES_SINCE_DUMP

    if resp.status != 200 or resp.raw_response is None:
        return []
    content = resp.raw_response.content
    if not content or len(content) > 5_000_000:
        return []

    canonical = urldefrag(resp.url or url)[0]
    if canonical in UNIQUE_URLS:
        return _extract_links(resp.url or url, content)

    try:
        soup = BeautifulSoup(content, "lxml")
    except Exception:
        return []

    tokens = _tokenize(soup)
    if len(tokens) < 20:
        return []

    digest = hashlib.sha256(" ".join(tokens).encode()).hexdigest()
    if digest in CONTENT_HASHES:
        return _extract_links(resp.url or url, content)
    CONTENT_HASHES.add(digest)

    UNIQUE_URLS.add(canonical)

    if len(tokens) > LONGEST["count"]:
        LONGEST["url"] = canonical
        LONGEST["count"] = len(tokens)

    for tok in tokens:
        if tok not in STOPWORDS and not tok.isdigit() and len(tok) > 1:
            WORD_COUNTS[tok] += 1

    host = urlparse(canonical).hostname
    if host:
        host = host.lower()
        if host.endswith(".uci.edu"):
            SUBDOMAIN_COUNTS[host].add(canonical)

    _PAGES_SINCE_DUMP += 1
    if _PAGES_SINCE_DUMP % 25 == 0:
        dump_report()

    return _extract_links(resp.url or url, content)


def is_valid(url):
    try:
        url = urldefrag(url)[0]
        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            return False

        host = (parsed.hostname or "").lower()
        if not any(host == d.lstrip(".") or host.endswith(d) for d in _ALLOWED_DOMAINS):
            return False

        path = parsed.path.lower()

        if _EXT_RE.match(path):
            return False
        if len(url) > 300:
            return False
        if _CALENDAR_RE.search(path):
            return False
        if _DATE_RE.search(path):
            return False
        if _AUTH_RE.search(url):
            return False

        path_segments = [s for s in path.split("/") if s]
        if any(seg in _VCS_SEGMENTS for seg in path_segments):
            return False
        if len(path_segments) > 8:
            return False
        if any(v >= 3 for v in collections.Counter(path_segments).values()):
            return False

        query = parsed.query.lower()
        if query:
            params = dict(
                p.split("=", 1) if "=" in p else (p, "")
                for p in query.split("&") if p
            )
            if _TRAP_PARAMS & set(params.keys()):
                return False
            for pname in ("page", "start", "offset", "p"):
                if pname in params:
                    try:
                        if int(params[pname]) > 50:
                            return False
                    except ValueError:
                        pass
            if len(params) > 4:
                return False

        return True

    except (ValueError, TypeError):
        return False


def dump_report():
    try:
        lines = []
        lines.append("=" * 70)
        lines.append("CRAWLER REPORT")
        lines.append("=" * 70)
        lines.append(f"\n[1] Unique pages found: {len(UNIQUE_URLS)}\n")
        lines.append("[2] Longest page by word count:")
        if LONGEST["url"]:
            lines.append(f"    URL:   {LONGEST['url']}")
            lines.append(f"    Words: {LONGEST['count']}")
        else:
            lines.append("    (no pages processed yet)")
        lines.append("")
        lines.append("[3] Top 50 most common words (stop words excluded):")
        for rank, (word, count) in enumerate(
            sorted(WORD_COUNTS.items(), key=lambda x: (-x[1], x[0]))[:50], 1
        ):
            lines.append(f"    {rank:>2}. {word}, {count}")
        lines.append("")
        lines.append("[4] Subdomains in *.uci.edu (alphabetical):")
        for host in sorted(SUBDOMAIN_COUNTS.keys()):
            lines.append(f"    {host}, {len(SUBDOMAIN_COUNTS[host])}")
        lines.append("")
        with open("crawler_report.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        print(f"[scraper] Warning: could not write report: {e}")


atexit.register(dump_report)


def _tokenize(soup):
    text = soup.get_text(separator=" ", strip=True)
    return [t for t in re.findall(r"[a-z][a-z']*", text.lower()) if len(t) > 1]


def _normalize_url(raw):
    parsed = urlparse(raw)
    return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower()).geturl()


def _extract_links(base_url, content):
    try:
        soup = BeautifulSoup(content, "lxml")
    except Exception:
        return []
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        try:
            full = urldefrag(urljoin(base_url, href))[0]
            links.append(_normalize_url(full))
        except Exception:
            continue
    return links
