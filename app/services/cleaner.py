import re
from bs4 import BeautifulSoup


def clean_email(raw_text: str) -> str:
    soup = BeautifulSoup(raw_text, "html.parser")

    for tag in soup(["script", "style", "img", "a"]):
        tag.decompose()

    text = soup.get_text(separator=" ")

    # Remove common unsubscribe/footer patterns
    text = re.sub(r"(?i)unsubscribe.*", "", text)
    text = re.sub(r"(?i)view\s+in\s+browser.*", "", text)
    text = re.sub(r"(?i)manage\s+preferences.*", "", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text
