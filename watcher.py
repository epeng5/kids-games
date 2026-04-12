"""
Auto-deploy watcher for kids' games.
Polls Open WebUI for new assistant messages containing HTML code blocks,
saves them to the local git repo, and auto-pushes to GitHub Pages.

Usage:
  python watcher.py --api-key YOUR_OPEN_WEBUI_API_KEY --repo-path C:\kids-games

First-time setup:
  1. Generate an API key from Open WebUI (Admin account → Settings → Account → API Keys)
  2. Start a chat for each kid and note the chat IDs from the URL bar
  3. Run this script with those chat IDs configured below
"""

import argparse
import json
import os
import re
import subprocess
import time
import requests
from datetime import datetime

# ── Configuration ───────────────────────────────────────────────────────
OPEN_WEBUI_URL = "http://localhost:3004"  # Adjust port if different
POLL_INTERVAL = 5  # seconds between checks

# Map chat IDs to output files. 
# Find chat IDs from the URL when you open each kid's chat:
# e.g., http://localhost:3004/c/abc123-def456 → chat_id is "abc123-def456"
# Update these after creating the kids' chats:
CHAT_FILE_MAP = {
    # "PASTE_CHANCE_CHAT_ID_HERE": "chance/index.html",
    # "PASTE_SAGE_CHAT_ID_HERE": "sage/index.html",
}

# ── HTML extraction ─────────────────────────────────────────────────────
def extract_html_from_message(content):
    """Extract HTML code from markdown code blocks in assistant message."""
    # Match ```html ... ``` blocks
    patterns = [
        r'```html\s*\n(.*?)```',
        r'```HTML\s*\n(.*?)```',
        r'```\s*\n(<!DOCTYPE html.*?)```',
        r'```\s*\n(<html.*?)```',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
        if matches:
            # Return the longest match (most likely the full file)
            return max(matches, key=len).strip()
    return None

# ── Open WebUI API ──────────────────────────────────────────────────────
def get_chat(api_key, chat_id):
    """Fetch a specific chat's full message history."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.get(
            f"{OPEN_WEBUI_URL}/api/v1/chats/{chat_id}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  [!] Failed to fetch chat {chat_id}: {resp.status_code}")
            return None
    except requests.RequestException as e:
        print(f"  [!] Error fetching chat {chat_id}: {e}")
        return None

def get_latest_assistant_html(chat_data):
    """Extract the most recent assistant message containing HTML."""
    if not chat_data or "chat" not in chat_data:
        return None, None
    
    messages = chat_data.get("chat", {}).get("messages", [])
    
    # Walk backwards through messages to find the latest assistant message with HTML
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            html = extract_html_from_message(content)
            if html:
                # Use message ID as version identifier
                msg_id = msg.get("id", "unknown")
                return html, msg_id
    
    return None, None

# ── Git operations ──────────────────────────────────────────────────────
def git_commit_and_push(repo_path, file_path, message="auto-update"):
    """Commit and push changes to GitHub."""
    try:
        subprocess.run(
            ["git", "add", file_path],
            cwd=repo_path, capture_output=True, check=True,
        )
        # Check if there are actual changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_path, capture_output=True,
        )
        if result.returncode == 0:
            # No changes staged
            return False
        
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_path, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "push"],
            cwd=repo_path, capture_output=True, check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [!] Git error: {e}")
        return False

# ── Main loop ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Watch Open WebUI and auto-deploy to GitHub Pages")
    parser.add_argument("--api-key", required=True, help="Open WebUI API key")
    parser.add_argument("--repo-path", required=True, help="Path to local git repo (e.g., C:\\kids-games)")
    parser.add_argument("--url", default=OPEN_WEBUI_URL, help="Open WebUI URL")
    args = parser.parse_args()

    global OPEN_WEBUI_URL
    OPEN_WEBUI_URL = args.url.rstrip("/")

    if not CHAT_FILE_MAP:
        print("=" * 60)
        print("ERROR: No chat IDs configured!")
        print()
        print("Edit this script and fill in CHAT_FILE_MAP with your chat IDs.")
        print("Find chat IDs from the URL bar when you open each kid's chat:")
        print("  http://localhost:3004/c/CHAT_ID_IS_HERE")
        print()
        print("Example:")
        print('  CHAT_FILE_MAP = {')
        print('      "abc123-def456-...": "chance/index.html",')
        print('      "xyz789-ghi012-...": "sage/index.html",')
        print('  }')
        print("=" * 60)
        return

    # Track last seen message IDs to avoid re-processing
    last_seen = {chat_id: None for chat_id in CHAT_FILE_MAP}

    print(f"🔍 Watching {len(CHAT_FILE_MAP)} chats for HTML updates...")
    print(f"   Open WebUI: {OPEN_WEBUI_URL}")
    print(f"   Repo path:  {args.repo_path}")
    print(f"   Polling every {POLL_INTERVAL}s")
    print()

    for chat_id, file_path in CHAT_FILE_MAP.items():
        kid_name = file_path.split("/")[0].capitalize()
        print(f"   {kid_name}: chat {chat_id[:12]}... → {file_path}")
    
    print()
    print("Press Ctrl+C to stop.")
    print()

    while True:
        try:
            for chat_id, file_path in CHAT_FILE_MAP.items():
                kid_name = file_path.split("/")[0].capitalize()
                
                chat_data = get_chat(args.api_key, chat_id)
                if not chat_data:
                    continue

                html, msg_id = get_latest_assistant_html(chat_data)
                
                if html and msg_id != last_seen[chat_id]:
                    # New HTML detected!
                    full_path = os.path.join(args.repo_path, file_path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(html)
                    
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"  [{timestamp}] 📝 New HTML for {kid_name} ({len(html)} chars)")
                    
                    # Auto-commit and push
                    pushed = git_commit_and_push(
                        args.repo_path,
                        file_path,
                        f"Update {kid_name}'s game - {timestamp}",
                    )
                    
                    if pushed:
                        print(f"  [{timestamp}] 🚀 Pushed to GitHub! Live in ~30s")
                    
                    last_seen[chat_id] = msg_id

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n👋 Stopped watching.")
            break
        except Exception as e:
            print(f"  [!] Unexpected error: {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
