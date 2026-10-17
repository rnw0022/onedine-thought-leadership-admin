#!/usr/bin/env python3
"""Poll the Render admin app for new submissions, publish them to the preview site."""
import json
import os
import re
import subprocess
import sys
import urllib.request

RENDER_URL = "https://onedine-thought-leadership-admin-pjxi.onrender.com"
WEB_DIR = os.path.expanduser("~/workspace/od-repo-build/web")
CONTENT_DIR = os.path.join(WEB_DIR, "src/content/blog")
PRESS_DIR = os.path.join(WEB_DIR, "src/content/press")
NEWS_DIR = os.path.join(WEB_DIR, "src/content/news")
OTHER_QUEUE = os.path.expanduser("~/workspace/od-admin/other-requests.md")
PREVIEW_SITE_ID = "111a636f-b9a7-4f79-b41f-40ea316c7c28"
NETLIFY_PY = os.path.expanduser("~/workspace/skills/netlify/bin/netlify.py")
DYNAMIC_CREDS = "/opt/muse/skills/custom-connector-setup/bin"


def slugify(title):
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:80]


def download_image(sub, slug):
    """Download a submission's hero image into the site's public images."""
    if not sub.get("hero_image"):
        return None
    try:
        img_url = f"{RENDER_URL}/uploads/{sub['hero_image']}"
        ext = os.path.splitext(sub["hero_image"])[1]
        local_name = f"{slug}{ext}"
        local_path = os.path.join(
            os.path.expanduser("~/workspace/od-repo-build/web/public/images"),
            local_name
        )
        with urllib.request.urlopen(img_url, timeout=60) as r, open(local_path, "wb") as f:
            f.write(r.read())
        print(f"  Downloaded image: {local_name}")
        return f"/images/{local_name}"
    except Exception as e:
        print(f"  Image download failed: {e}")
        return None


def publish_thought_leadership(sub):
    title = sub["title"]
    slug = slugify(title)
    read_time = max(1, round(len(sub["body"].split()) / 200))
    image_path = download_image(sub, slug)
    hero_line = f'\nheroImage: "{image_path}"' if image_path else ""
    md = f"""---
title: "{title}"
excerpt: "{sub['excerpt']}"
category: "Thought Leadership"
author: "{sub['author']}"
date: {sub['go_live']}
readTime: {read_time}{hero_line}
---

{sub['body']}
"""
    path = os.path.join(CONTENT_DIR, f"{slug}.md")
    with open(path, "w") as f:
        f.write(md)
    print(f"  Wrote blog/{slug}.md")
    return title


def publish_press_or_news(sub, kind):
    """kind is 'press' or 'news'; writes to the matching content collection."""
    title = sub["title"]
    slug = slugify(title)
    image_path = download_image(sub, slug)
    image_line = f'\nimage: "{image_path}"' if image_path else ""
    url_line = f'\nurl: "{sub["url"]}"' if sub.get("url") else ""
    md = f"""---
title: "{title}"
publication: "{sub.get('publication', 'OneDine')}"
date: {sub.get('date')}{url_line}{image_line}
---

"""
    dest = PRESS_DIR if kind == "press" else NEWS_DIR
    os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, f"{slug}.md")
    with open(path, "w") as f:
        f.write(md)
    print(f"  Wrote {kind}/{slug}.md")
    return title


def queue_other(sub):
    """Other requests go to a manual-review queue file, surfaced to Ryan."""
    os.makedirs(os.path.dirname(OTHER_QUEUE), exist_ok=True)
    entry = f"\n## {sub.get('submitted_at', '')} - {sub.get('title', '(no title)')}\n\n{sub.get('body', '')}\n"
    with open(OTHER_QUEUE, "a") as f:
        f.write(entry)
    print(f"  Queued 'other' request: {sub.get('title')}")
    return sub.get("title", "(no title)")


def main():
    # Fetch pending submissions
    try:
        with urllib.request.urlopen(f"{RENDER_URL}/api/pending", timeout=30) as resp:
            submissions = json.loads(resp.read())
    except Exception as e:
        print(f"Failed to fetch: {e}")
        return 1

    if not submissions:
        print("No pending submissions.")
        return 0

    print(f"Found {len(submissions)} pending submission(s).")
    published = []
    other_requests = []

    for sub in submissions:
        # Default to thought-leadership for submissions from before the type dropdown existed
        ctype = sub.get("content_type", "thought-leadership")
        try:
            if ctype == "thought-leadership":
                published.append(publish_thought_leadership(sub))
            elif ctype in ("press", "news"):
                published.append(publish_press_or_news(sub, ctype))
            elif ctype == "other":
                other_requests.append(queue_other(sub))
                published.append(sub.get("title", "(no title)"))
            else:
                print(f"  Unknown content type '{ctype}', skipping: {sub.get('title')}")
        except Exception as e:
            print(f"  Failed to publish '{sub.get('title')}': {e}")

    if not published:
        print("Nothing published.")
        return 0

    # Rebuild
    print("Rebuilding...")
    build = subprocess.run(
        ["bun", "run", "--cwd", "web", "build"],
        cwd=os.path.expanduser("~/workspace/od-repo-build"),
        capture_output=True, text=True, timeout=180,
    )
    if build.returncode != 0:
        print(f"Build failed: {build.stderr[-1000:]}")
        return 1
    print("Build succeeded.")

    # Deploy to preview
    print("Deploying to preview...")
    env = dict(os.environ, PYTHONPATH=DYNAMIC_CREDS)
    deploy = subprocess.run(
        [sys.executable, NETLIFY_PY, "deploy",
         "--site-id", PREVIEW_SITE_ID,
         "--dir", os.path.join(WEB_DIR, "dist")],
        capture_output=True, text=True, timeout=300, env=env,
    )
    if deploy.returncode != 0:
        print(f"Deploy failed: {deploy.stderr[-1000:]}")
        return 1
    print("Deployed to preview.")

    # Ack processed submissions
    try:
        data = json.dumps({"titles": published}).encode()
        req = urllib.request.Request(
            f"{RENDER_URL}/api/ack", data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=30):
            pass
        print(f"Acked {len(published)} submission(s).")
    except Exception as e:
        print(f"Ack failed (will retry next run): {e}")

    if other_requests:
        print(f"OTHER REQUESTS needing manual review ({len(other_requests)}):")
        for t in other_requests:
            print(f"  - {t}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
