"""Holiday names from the school calendar look like 'Winter Break / إجازة الشتاء'. Word files are in English."""
import re


def english_name(name: str) -> str:
    parts = [p for p in str(name or "").split(" / ") if not re.search(r"[؀-ۿ]", p)]
    return (parts[0] if parts else str(name or "")).strip()
