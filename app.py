#!/usr/bin/env python3
"""Simple content submission interface for OneDine execs.

Execs fill out a form, pick their name from a dropdown, and hit submit.
Submissions are queued and picked up by the publisher on the main server.
"""
import json
import os
import re
from datetime import date
from flask import Flask, request, redirect, render_template_string, jsonify

app = Flask(__name__)

AUTHORS = [
    "Rom Krupp",
    "Vance Miller",
    "Amar Pai",
    "Richelle Franklin",
    "Mike Block",
    "Rob West",
    "Angela Diffly",
    "OneDine",
]

SUBMISSIONS_FILE = os.path.join(os.path.dirname(__file__), "submissions.json")


def load_submissions():
    if os.path.exists(SUBMISSIONS_FILE):
        with open(SUBMISSIONS_FILE) as f:
            return json.load(f)
    return []


def save_submissions(subs):
    with open(SUBMISSIONS_FILE, "w") as f:
        json.dump(subs, f, indent=2)

FORM_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OneDine Thought Leadership - New Post</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; }
  h1 { font-size: 1.8rem; }
  label { display: block; font-weight: 600; margin: 20px 0 6px; }
  input, select, textarea { width: 100%; padding: 10px; font-size: 1rem; border: 1px solid #ccc; border-radius: 8px; box-sizing: border-box; }
  textarea { min-height: 300px; font-family: inherit; line-height: 1.5; }
  button { margin-top: 24px; padding: 12px 32px; font-size: 1.1rem; background: #AD202C; color: white; border: none; border-radius: 8px; cursor: pointer; }
  button:hover { background: #8e1a24; }
  .hint { color: #666; font-size: 0.9rem; margin-top: 4px; }
  .success { background: #e6f4ea; border: 1px solid #34a853; padding: 16px; border-radius: 8px; margin-bottom: 20px; }
</style>
</head>
<body>
  <h1>New Thought Leadership Post</h1>
  {% if success %}
  <div class="success">Posted! It is now live on the <a href="https://onedine-preview.netlify.app/blog/">preview site</a> for review.</div>
  {% endif %}
  <form method="POST" enctype="multipart/form-data">
    <label for="title">Title</label>
    <input type="text" id="title" name="title" required placeholder="Your headline">

    <label for="author">Author</label>
    <select id="author" name="author" required>
      {% for a in authors %}
      <option value="{{ a }}">{{ a }}</option>
      {% endfor %}
    </select>

    <label for="excerpt">Summary</label>
    <input type="text" id="excerpt" name="excerpt" required placeholder="One or two sentences for the card preview">
    <p class="hint">This shows on the Thought Leadership page under your title.</p>

    <label for="go_live">When should this go live?</label>
    <input type="date" id="go_live" name="go_live" required>
    <p class="hint">Pick the date you want this published. Use this to coordinate with your LinkedIn posts.</p>

    <label for="body">Your post</label>
    <textarea id="body" name="body" required placeholder="Write your piece here. Blank lines separate paragraphs."></textarea>
    <p class="hint">Plain text is fine. Use blank lines between paragraphs.</p>

    <label for="image">Hero image (optional)</label>
    <input type="file" id="image" name="image" accept="image/*">
    <p class="hint">Upload a header image for your post. Shows at the top of the article.</p>

    <button type="submit">Publish to Preview</button>
  </form>
</body>
</html>
"""


def slugify(title):
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:80]


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        title = request.form["title"].strip()
        author = request.form["author"].strip()
        excerpt = request.form["excerpt"].strip()
        body = request.form["body"].strip()
        go_live = request.form.get("go_live", "").strip() or date.today().isoformat()

        if author not in AUTHORS:
            return "Invalid author", 400

        # Handle image upload
        hero_image = None
        if "image" in request.files:
            f = request.files["image"]
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                    safe_name = f"{slugify(title)}{ext}"
                    upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
                    os.makedirs(upload_dir, exist_ok=True)
                    f.save(os.path.join(upload_dir, safe_name))
                    hero_image = safe_name

        subs = load_submissions()
        subs.append({
            "title": title,
            "author": author,
            "excerpt": excerpt,
            "body": body,
            "go_live": go_live,
            "hero_image": hero_image,
            "submitted_at": date.today().isoformat(),
            "published": False,
        })
        save_submissions(subs)

        return redirect("/?success=1")

    return render_template_string(
        FORM_HTML, authors=AUTHORS, success=request.args.get("success")
    )


@app.route("/api/pending")
def pending():
    """Return unprocessed submissions for the publisher to pick up."""
    subs = load_submissions()
    return jsonify([s for s in subs if not s.get("published")])


@app.route("/api/ack", methods=["POST"])
def ack():
    """Mark submissions as published."""
    data = request.get_json(force=True)
    titles = set(data.get("titles", []))
    subs = load_submissions()
    for s in subs:
        if s["title"] in titles:
            s["published"] = True
    save_submissions(subs)
    return jsonify({"ok": True})


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """Serve uploaded hero images for the publisher to fetch."""
    from flask import send_from_directory
    upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
    return send_from_directory(upload_dir, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8899)
