import sys
import os
import json
import re
from typing import Tuple, List

workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MOCK_DICTIONARY_PATTERNS = [
    r'["\']examplecorp["\']',
    r'["\']founded=2010["\']',
    r'["\']dummy_claim["\']'
]

def validate_marketplace() -> Tuple[bool, List[str]]:
    errors = []

    # 1. Check marketplace.json
    manifest_path = os.path.join(workspace_root, "marketplace.json")
    if not os.path.exists(manifest_path):
        errors.append("marketplace.json missing from workspace root.")
        return False, errors

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception as e:
        errors.append(f"marketplace.json is invalid JSON: {e}")
        return False, errors

    skills = manifest.get("skills", [])
    if not skills:
        errors.append("marketplace.json contains no skills.")
        return False, errors

    # 2. Check Entrypoint
    entrypoints = [s for s in skills if s.get("entrypoint") is True]
    if len(entrypoints) != 1:
        errors.append(f"Marketplace must have exactly 1 entrypoint skill. Found {len(entrypoints)}.")
    elif entrypoints[0].get("name") != "audit-orchestrator":
        errors.append(f"Entrypoint skill must be 'audit-orchestrator', found '{entrypoints[0].get('name')}'.")

    # 3. Check declared skill folders & SKILL.md
    for s in skills:
        name = s.get("name")
        rel_path = s.get("path")
        if not name or not rel_path:
            errors.append(f"Skill entry missing 'name' or 'path': {s}")
            continue

        if os.path.isabs(rel_path):
            errors.append(f"Skill path for '{name}' must be relative, found absolute path '{rel_path}'.")

        full_skill_dir = os.path.join(workspace_root, rel_path)
        if not os.path.exists(full_skill_dir):
            errors.append(f"Declared skill directory missing: {rel_path}")
            continue

        skill_md_path = os.path.join(full_skill_dir, "SKILL.md")
        if not os.path.exists(skill_md_path):
            errors.append(f"SKILL.md missing in {rel_path}")
            continue

        with open(skill_md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.startswith("---"):
            errors.append(f"SKILL.md in {rel_path} lacks valid YAML frontmatter opening '---'.")

        if "name:" not in content or "description:" not in content:
            errors.append(f"SKILL.md in {rel_path} frontmatter missing 'name' or 'description'.")

    # 4. Check for absolute path leaks, mock dictionaries, or exposed credentials
    secret_regex = re.compile(r'AIzaSy[A-Za-z0-9_-]{33}')
    user_token = "/" + "Users" + "/" + "priyansubaliarsingh"
    file_proto = "file" + "://" + "/"
    abs_path_regex = re.compile(rf'({re.escape(file_proto)}|{re.escape(user_token)}|/home/[a-z0-9]+/|/Desktop/)')

    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in ['.git', 'venv', '.venv', '__pycache__', '.pytest_cache', 'scratch']]
        for file in files:
            if file == "validate_marketplace.py":
                continue
            if file.endswith(('.py', '.json', '.md', '.html', '.css', '.js')):
                fp = os.path.join(root, file)
                try:
                    with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                        txt = f.read()
                        if secret_regex.search(txt):
                            errors.append(f"Exposed API key found in {os.path.relpath(fp, workspace_root)}")
                        if abs_path_regex.search(txt):
                            errors.append(f"Hardcoded absolute path found in {os.path.relpath(fp, workspace_root)}")
                        for mock_pat in MOCK_DICTIONARY_PATTERNS:
                            if re.search(mock_pat, txt, re.I):
                                errors.append(f"Hardcoded mock company pattern found in {os.path.relpath(fp, workspace_root)}")
                except Exception:
                    pass

    # 5. Check README.md
    readme_path = os.path.join(workspace_root, "README.md")
    if not os.path.exists(readme_path):
        errors.append("README.md missing from workspace root.")

    is_valid = (len(errors) == 0)
    return is_valid, errors

def main():
    print("=== AGENTSKILLS.IO MARKETPLACE HYGIENE VALIDATOR ===")
    valid, errors = validate_marketplace()
    if valid:
        print("RESULT: SUCCESS — Marketplace is 100% compliant with agentskills.io standard!")
        sys.exit(0)
    else:
        print(f"RESULT: FAILED — Found {len(errors)} validation errors:")
        for err in errors:
            print(f"  ❌ {err}")
        sys.exit(1)

if __name__ == "__main__":
    main()
