import re
from bs4 import BeautifulSoup

# Patterns that signal the start of footer boilerplate — everything after is dropped
_FOOTER_PATTERNS = [
    r"unsubscribe",
    r"view\s+in\s+(your\s+)?browser",
    r"manage\s+(your\s+)?preferences",
    r"manage\s+(your\s+)?subscriptions",
    r"you('re|\s+are)\s+receiving\s+this",
    r"you\s+received\s+this\s+(email|newsletter)",
    r"this\s+email\s+was\s+sent\s+to",
    r"to\s+stop\s+receiving",
    r"opt[\s-]out",
    r"privacy\s+policy",
    r"©\s*\d{4}",
    r"all\s+rights\s+reserved",
    r"our\s+mailing\s+address",
    r"forwarded\s+this\s+email",
    r"read\s+(this\s+)?online",
    r"having\s+trouble\s+viewing",
]

_FOOTER_RE = re.compile(
    r"(?i)(" + "|".join(_FOOTER_PATTERNS) + r").*",
    re.DOTALL,
)

# Tracking pixel / beacon URLs left as stray text after tag removal
_URL_RE = re.compile(r"https?://\S+")


def clean_email(raw_text: str) -> str:
    if _is_html(raw_text):
        text = _strip_html(raw_text)
    else:
        text = raw_text

    text = _FOOTER_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _is_html(text: str) -> bool:
    return bool(re.search(r"<[a-zA-Z][\s\S]*?>", text))


def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "img", "a", "head"]):
        tag.decompose()

    return soup.get_text(separator=" ")
