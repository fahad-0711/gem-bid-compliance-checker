"""
Helper functions for viewing and safely editing rules.json through the UI,
without requiring direct file/code access.
"""

import json
import os
import shutil
from datetime import datetime

RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")


def read_rules_raw() -> str:
    """Returns the rules.json file content as a raw string, for display/editing."""
    with open(RULES_PATH, "r") as f:
        return f.read()


def validate_rules_json(raw_text: str) -> tuple[bool, str]:
    """
    Checks that the given text is valid JSON and has the expected top-level shape.
    Returns (is_valid, error_message).
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"

    if "mandatory_documents" not in data:
        return False, "Missing required key: 'mandatory_documents'"

    for doc_type, config in data.items():
        if doc_type == "mandatory_documents":
            continue
        if "rules" not in config:
            return False, f"Document type '{doc_type}' is missing a 'rules' list"
        for rule in config["rules"]:
            if "field" not in rule or "type" not in rule or "error" not in rule:
                return False, f"A rule under '{doc_type}' is missing 'field', 'type', or 'error'"

    return True, ""


def save_rules(raw_text: str) -> tuple[bool, str]:
    """
    Validates and saves new rules content, backing up the previous version first.
    Returns (success, message).
    """
    is_valid, error = validate_rules_json(raw_text)
    if not is_valid:
        return False, error

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"rules_{timestamp}.json")
    shutil.copy(RULES_PATH, backup_path)

    with open(RULES_PATH, "w") as f:
        f.write(raw_text)

    return True, f"Rules saved. Previous version backed up to backups/rules_{timestamp}.json"


def list_backups() -> list:
    """Returns available backup filenames, most recent first."""
    if not os.path.exists(BACKUP_DIR):
        return []
    files = sorted(os.listdir(BACKUP_DIR), reverse=True)
    return files


def restore_backup(filename: str) -> tuple[bool, str]:
    """Restores rules.json from a chosen backup file."""
    backup_path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(backup_path):
        return False, "Backup file not found."
    shutil.copy(backup_path, RULES_PATH)
    return True, f"Restored rules from {filename}"