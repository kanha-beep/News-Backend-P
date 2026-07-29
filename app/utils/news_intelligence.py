import re
from datetime import datetime
from urllib.parse import urlparse


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in",
    "is", "it", "of", "on", "or", "that", "the", "to", "was", "were", "will", "with",
}
MAX_TAG_LENGTH = 10
EXCLUDED_TAGS = {"photo", "photos"}


def escape_regex(value: str) -> str:
    return re.escape(value)


def normalize_tag_value(value: str = "") -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"^-+|-+$", "", value)


def sanitize_tags(values) -> list[str]:
    if not isinstance(values, list):
        values = [values]
    seen = []
    for raw_value in values:
        tag = normalize_tag_value(raw_value)
        if (
            tag
            and tag not in EXCLUDED_TAGS
            and len(tag) <= MAX_TAG_LENGTH
            and tag not in {"general", "news", "latest-news"}
            and tag not in seen
        ):
            seen.append(tag)
    return seen


def normalize_title_key(value: str = "") -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_published_at(pub_date: str | None):
    if not pub_date:
        return None
    for candidate in (pub_date, pub_date.replace(" GMT", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(pub_date)
    except Exception:
        return None


def build_date_keys(published_at):
    if not published_at:
        return {"publishedDateKey": "", "publishedMonthKey": ""}
    return {
        "publishedDateKey": published_at.strftime("%Y-%m-%d"),
        "publishedMonthKey": published_at.strftime("%Y-%m"),
    }


def get_category_details(url_str: str):
    try:
        segments = [segment for segment in urlparse(url_str).path.split("/") if segment]
        return {
            "level1": segments[0] if segments else "general",
            "level2": segments[1] if len(segments) > 1 else None,
            "level3": segments[2] if len(segments) > 2 else None,
        }
    except Exception:
        return {"level1": "general", "level2": None, "level3": None}


def tokenize(value: str = "") -> list[str]:
    tokens = re.sub(r"[^a-z0-9\s]", " ", value.lower()).split()
    return [token for token in tokens if token and token not in STOP_WORDS]


def build_fingerprint(title: str = "") -> str:
    return "-".join(tokenize(title)[:8])


def extract_entities(article: dict) -> list[str]:
    text = f"{article.get('title', '')} {article.get('description', '')}"
    matches = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", text)
    seen = []
    for item in matches:
        if item not in seen:
            seen.append(item)
    return seen[:8]


def get_tags(item: dict) -> list[str]:
    title = item.get("title", "").lower()
    desc = item.get("description", "").lower()
    url = item.get("link", "").lower()
    text = f"{title} {desc}"
    tags = []
    if "/sport/" in url:
        tags.append("sports")
    if "/news/international/" in url:
        tags.append("international")
    if "/business/" in url:
        tags.append("economy")
    if "/opinion/" in url:
        tags.append("opinion")
    if re.search(r"(minister|cabinet|parliament|bjp|congress|election|chief minister|prime minister)", text):
        tags.append("politics")
    if re.search(r"(student|exam|university|admission|school|cet)", text):
        tags.append("education")
    if re.search(r"(arrest|assault|murder|theft|robbery|police|court|case)", text):
        tags.append("crime")
    if re.search(r"(ganja|narcotic|drug|contraband|smuggling)", text):
        tags.append("drugs")
    if re.search(r"(hospital|doctor|health|disease|vaccine)", text):
        tags.append("health")
    return sanitize_tags(tags)


def infer_fallback_tags(item: dict) -> list[str]:
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    url = item.get("link", "").lower()
    fallback_tags = []

    def push_tag(value):
        normalized = normalize_tag_value(value)
        if normalized:
            fallback_tags.append(normalized)

    push_tag(item.get("category"))
    push_tag(item.get("subCategory"))

    keyword_fallbacks = [
        ("technology", r"(ai|artificial intelligence|tech|software|startup|semiconductor|chip|app|digital|cyber)"),
        ("science", r"(research|scientist|space|nasa|isro|climate|species|physics|chemistry|biology)"),
        ("environment", r"(forest|wildlife|climate|rainfall|pollution|river|water|conservation|ecology)"),
        ("economy", r"(economy|inflation|gdp|market|stock|trade|rupee|finance|bank|industry)"),
        ("urban", r"(city|cities|urban|municipal|metro|infrastructure|civic|housing|public transport|traffic)"),
        ("water", r"(water crisis|drinking water|groundwater|sewage|drainage|reservoir|lake|river)"),
        ("climate", r"(heat wave|global warming|emissions|carbon|sustainability|green energy|extreme weather)"),
        ("agriculture", r"(farmer|farmers|crop|harvest|paddy|monsoon|agriculture|agri)"),
        ("sports", r"(cricket|football|hockey|tennis|olympic|match|tournament|fifa|ipl)"),
        ("entertainment", r"(film|movie|actor|actress|music|song|cinema|show|festival)"),
        ("law", r"(supreme court|high court|tribunal|judgment|verdict|legal|law)"),
        ("opinion", r"(analysis|explained|opinion|editorial|column|commentary|five solutions|why|how to)"),
        ("travel", r"(tourism|travel|airport|flight|railway|train|destination)"),
    ]
    for tag, pattern in keyword_fallbacks:
        if re.search(pattern, text) or re.search(pattern, url):
            fallback_tags.append(tag)
    return sanitize_tags(fallback_tags)[:6]


def normalize_feed_item(item: dict, feed_context: dict | None = None) -> dict:
    feed_context = feed_context or {}
    published_at = parse_published_at(item.get("pubDate"))
    date_keys = build_date_keys(published_at)
    category = get_category_details(item.get("link", ""))
    try:
        source_domain = urlparse(item.get("link", "")).hostname or "unknown"
        source_domain = re.sub(r"^www\.", "", source_domain)
    except Exception:
        source_domain = "unknown"

    normalized = {
        "title": item.get("title", "") or "",
        "link": item.get("link", ""),
        "canonicalLink": item.get("link", ""),
        "pubDate": item.get("pubDate", "") or "",
        "publishedAt": published_at,
        "publishedDateKey": date_keys["publishedDateKey"],
        "publishedMonthKey": date_keys["publishedMonthKey"],
        "description": item.get("description", "") or "",
        "guid": item.get("guid", "") or "",
        "category": category["level1"],
        "subCategory": category["level2"],
        "tags": [],
        "sourceName": feed_context.get("sourceName") or feed_context.get("title") or "Unknown source",
        "sourceDomain": source_domain,
        "normalizedTitle": normalize_title_key(item.get("title", "") or ""),
        "fingerprint": build_fingerprint(item.get("title", "") or item.get("link", "")),
        "entities": [],
        "duplicateLinks": [],
    }
    normalized["tags"] = get_tags(normalized) or infer_fallback_tags(normalized)
    normalized["entities"] = extract_entities(normalized)
    return normalized


def score_similarity(left_article: dict, right_article: dict) -> float:
    left_tokens = set(tokenize(f"{left_article.get('title', '')} {left_article.get('description', '')}"))
    right_tokens = set(tokenize(f"{right_article.get('title', '')} {right_article.get('description', '')}"))
    if not left_tokens or not right_tokens:
        return 0
    intersection = len(left_tokens & right_tokens)
    return intersection / max(len(left_tokens), len(right_tokens))


def build_neutral_summary(articles: list[dict]) -> str:
    latest = articles[0] if articles else {}
    entities = list(dict.fromkeys([entity for article in articles for entity in article.get("entities", [])]))[:3]
    tags = list(dict.fromkeys([tag for article in articles for tag in article.get("tags", [])]))[:3]
    parts = [
        latest.get("title") or "This event is evolving across multiple reports.",
        f"Key entities: {', '.join(entities)}." if entities else None,
        f"Coverage themes: {', '.join(tags)}." if tags else None,
        f"This cluster combines {len(articles)} related report{'s' if len(articles) != 1 else ''} into one evolving event.",
    ]
    return " ".join(part for part in parts if part)


def describe_coverage_shift(articles: list[dict]) -> str:
    if len(articles) < 2:
        return "Coverage is still emerging from a single report."
    earliest = articles[-1]
    latest = articles[0]
    earliest_tokens = set(tokenize(f"{earliest.get('title', '')} {earliest.get('description', '')}"))
    latest_tokens = set(tokenize(f"{latest.get('title', '')} {latest.get('description', '')}"))
    new_focus = [token for token in latest_tokens if token not in earliest_tokens][:4]
    if not new_focus:
        return "Coverage remains stable, with later reports reinforcing the same core facts."
    return f"Coverage shifted toward {', '.join(new_focus)} as the story developed."


def cluster_articles(articles: list[dict]) -> list[dict]:
    clusters = []
    for article in articles:
        matched_cluster = None
        for current_cluster in clusters:
            representative = current_cluster["articles"][0]
            if article.get("fingerprint") == representative.get("fingerprint") or score_similarity(article, representative) >= 0.45:
                matched_cluster = current_cluster
                break
        if matched_cluster:
            matched_cluster["articles"].append(article)
        else:
            clusters.append({"id": article.get("fingerprint") or str(article.get("_id")) or article.get("link"), "articles": [article]})

    shaped = []
    for cluster in clusters:
        sorted_articles = sorted(
            cluster["articles"],
            key=lambda article: article.get("publishedAt") or article.get("createdAt") or datetime.min,
            reverse=True,
        )
        latest = sorted_articles[0]
        earliest = sorted_articles[-1]
        all_tags = list(dict.fromkeys([tag for article in sorted_articles for tag in article.get("tags", [])]))[:6]
        all_entities = list(dict.fromkeys([entity for article in sorted_articles for entity in article.get("entities", [])]))[:10]
        source_count = len({article.get("sourceDomain") for article in sorted_articles if article.get("sourceDomain")})
        shaped.append(
            {
                "id": cluster["id"],
                "title": latest.get("title") or "Untitled event",
                "summary": build_neutral_summary(sorted_articles),
                "articleCount": len(sorted_articles),
                "sourceCount": source_count,
                "corroborationLabel": f"{source_count} sources are covering this event." if source_count > 1 else "This is currently a single-source signal.",
                "tags": all_tags,
                "entities": all_entities,
                "timeline": [
                    {
                        "title": article.get("title"),
                        "link": article.get("link"),
                        "publishedAt": article.get("publishedAt"),
                        "sourceName": article.get("sourceName"),
                        "sourceDomain": article.get("sourceDomain"),
                    }
                    for article in sorted_articles
                ],
                "coverageShift": describe_coverage_shift(sorted_articles),
                "startedAt": earliest.get("publishedAt") or earliest.get("createdAt"),
                "updatedAt": latest.get("publishedAt") or latest.get("createdAt"),
                "articles": sorted_articles,
            }
        )
    return sorted(shaped, key=lambda cluster: cluster.get("updatedAt") or datetime.min, reverse=True)


def score_semantic_match(article: dict, query: str) -> int:
    query_tokens = set(tokenize(query))
    article_tokens = set(tokenize(f"{article.get('title', '')} {article.get('description', '')} {' '.join(article.get('tags', []))}"))
    if not query_tokens or not article_tokens:
        return 0
    score = 0
    for token in query_tokens:
        if token in article_tokens:
            score += 12
    for entity in article.get("entities", []):
        if entity.lower() in query.lower():
            score += 18
    if query.lower() in article.get("title", "").lower():
        score += 25
    return score

