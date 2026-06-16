import pytest
from app.services.cleaner import clean_email

# --- Digital Digest style (HTML newsletter) ---
DIGITAL_DIGEST_HTML = """
<html><head><style>body{font-family:sans-serif}</style></head>
<body>
<img src="https://track.digitaldigest.me/open.gif" width="1" height="1"/>
<h1>Digital Digest #42</h1>
<p>Startup A raised $5M in a seed round led by Antler MENAP.</p>
<p>Startup B launched its fintech platform across the Gulf.</p>
<a href="https://digitaldigest.me/read-online">View in your browser</a>
<p>You're receiving this because you subscribed at digitaldigest.me.</p>
<p>Unsubscribe | Manage preferences</p>
<p>© 2024 Digital Digest. All rights reserved.</p>
</body></html>
"""

# --- Strictly VC style (plain text) ---
STRICTLY_VC_TEXT = """Strictly VC — Tuesday Edition

Andreessen Horowitz led a $20M Series A in a MENA-focused SaaS company.

Sequoia is reportedly looking at Gulf opportunities in the fintech space.

---
You received this email because you subscribed to Strictly VC.
To stop receiving these emails, click here: https://strictlyvc.com/unsubscribe?id=abc123
© 2024 Strictly VC
"""

# --- Term Sheet style (HTML with heavy footer) ---
TERM_SHEET_HTML = """
<html><body>
<p><strong>TERM SHEET</strong> — Fortune's daily venture capital briefing</p>
<p>Deal of the day: A Dubai-based healthtech raised $12M from regional VCs.</p>
<p>In other news, MENA startup exits are up 30% year-on-year.</p>
<table>
  <tr><td>This email was sent to you@example.com by Fortune Media.</td></tr>
  <tr><td><a href="#">Unsubscribe</a> | <a href="#">Privacy Policy</a></td></tr>
  <tr><td>© 2024 Fortune Media IP Limited. All rights reserved.</td></tr>
  <tr><td>Our mailing address: 225 Liberty St, New York, NY 10281</td></tr>
</table>
</body></html>
"""


def test_digital_digest_strips_html_tags():
    result = clean_email(DIGITAL_DIGEST_HTML)
    assert "<" not in result
    assert ">" not in result


def test_digital_digest_keeps_content():
    result = clean_email(DIGITAL_DIGEST_HTML)
    assert "Startup A raised $5M" in result
    assert "Startup B launched" in result


def test_digital_digest_strips_footer():
    result = clean_email(DIGITAL_DIGEST_HTML)
    assert "unsubscribe" not in result.lower()
    assert "receiving this" not in result.lower()
    assert "All rights reserved" not in result


def test_digital_digest_strips_tracking_urls():
    result = clean_email(DIGITAL_DIGEST_HTML)
    assert "track.digitaldigest.me" not in result


def test_strictly_vc_handles_plain_text():
    result = clean_email(STRICTLY_VC_TEXT)
    assert "Andreessen Horowitz" in result
    assert "Sequoia" in result


def test_strictly_vc_strips_footer():
    result = clean_email(STRICTLY_VC_TEXT)
    assert "unsubscribe" not in result.lower()
    assert "strictlyvc.com/unsubscribe" not in result


def test_term_sheet_keeps_content():
    result = clean_email(TERM_SHEET_HTML)
    assert "Dubai-based healthtech" in result
    assert "MENA startup exits" in result


def test_term_sheet_strips_footer():
    result = clean_email(TERM_SHEET_HTML)
    assert "Fortune Media" not in result
    assert "mailing address" not in result.lower()
    assert "Privacy Policy" not in result


def test_output_is_clean_prose():
    result = clean_email(DIGITAL_DIGEST_HTML)
    # No consecutive whitespace
    assert "  " not in result
    assert result == result.strip()


def test_empty_input():
    assert clean_email("") == ""


def test_plain_text_no_footer():
    text = "This is a simple newsletter with no footer."
    assert clean_email(text) == text
