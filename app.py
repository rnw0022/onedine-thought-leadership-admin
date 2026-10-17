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

CONTENT_TYPES = [
    ("press", "Press Announcements (Press Page)"),
    ("news", "Media Coverage (In the News page)"),
    ("thought-leadership", "Thought Leadership"),
    ("other", "Other (edits to something else)"),
]

FORM_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OneDine Web Assets to Post</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; }
  h1 { font-size: 1.8rem; }
  label { display: block; font-weight: 600; margin: 20px 0 6px; }
  input, select, textarea { width: 100%; padding: 10px; font-size: 1rem; border: 1px solid #ccc; border-radius: 8px; box-sizing: border-box; }
  textarea { min-height: 200px; font-family: inherit; line-height: 1.5; }
  button { margin-top: 24px; padding: 12px 32px; font-size: 1.1rem; background: #AD202C; color: white; border: none; border-radius: 8px; cursor: pointer; }
  button:hover { background: #8e1a24; }
  .hint { color: #666; font-size: 0.9rem; margin-top: 4px; }
  .success { background: #e6f4ea; border: 1px solid #34a853; padding: 16px; border-radius: 8px; margin-bottom: 20px; }
  .field-group { display: none; }
  .field-group.active { display: block; }
</style>
</head>
<body>
  <h1>Web Assets to Post</h1>
  <p class="hint">Submit new content or request edits for the OneDine site. Everything publishes to the preview site for review first.</p>
  {% if success %}
  <div class="success">Posted! It is now live on the <a href="https://onedine-preview.netlify.app/">preview site</a> for review.</div>
  {% endif %}
  <form method="POST" enctype="multipart/form-data">
    <label for="content_type">What are you posting?</label>
    <select id="content_type" name="content_type" required>
      {% for val, label in content_types %}
      <option value="{{ val }}">{{ label }}</option>
      {% endfor %}
    </select>

    <div class="field-group" data-for="press news">
      <label for="headline">Headline</label>
      <input type="text" id="headline" name="headline" placeholder="Announcement or article headline">

      <label for="publication">Publication / Source</label>
      <input type="text" id="publication" name="publication" placeholder="e.g. PR Newswire, Fast Company, OneDine">
      <p class="hint">For press announcements, this is usually "OneDine" or the wire service.</p>

      <label for="item_date">Date</label>
      <input type="date" id="item_date" name="item_date">

      <label for="item_url">Link URL</label>
      <input type="url" id="item_url" name="item_url" placeholder="https://...">
      <p class="hint">Link to the full announcement or article.</p>

      <label for="item_image">Thumbnail image (optional)</label>
      <input type="file" id="item_image" name="image" accept="image/*">
    </div>

    <div class="field-group active" data-for="thought-leadership">
      <label for="title">Title</label>
      <input type="text" id="title" name="title" placeholder="Your headline">

      <label for="author">Author</label>
      <select id="author" name="author">
        {% for a in authors %}
        <option value="{{ a }}">{{ a }}</option>
        {% endfor %}
      </select>

      <label for="excerpt">Summary</label>
      <input type="text" id="excerpt" name="excerpt" placeholder="One or two sentences for the card preview">
      <p class="hint">This shows on the Thought Leadership page under your title.</p>

      <label for="go_live">When should this go live?</label>
      <input type="date" id="go_live" name="go_live">
      <p class="hint">Pick the date you want this published. Use this to coordinate with your LinkedIn posts.</p>

      <label for="body">Your post</label>
      <textarea id="body" name="body" placeholder="Write your piece here. Blank lines separate paragraphs."></textarea>
      <p class="hint">Plain text is fine. Use blank lines between paragraphs.</p>

      <label for="tl_image">Hero image (optional)</label>
      <input type="file" id="tl_image" name="image" accept="image/*">
      <p class="hint">Upload a header image for your post. Shows at the top of the article and as the card thumbnail.</p>
    </div>

    <div class="field-group" data-for="other">
      <label for="other_title">What needs changing?</label>
      <input type="text" id="other_title" name="other_title" placeholder="e.g. Update homepage hero copy">

      <label for="other_details">Details</label>
      <textarea id="other_details" name="other_details" placeholder="Describe the edit or addition. Include the page, the current text, and what it should say."></textarea>
      <p class="hint">This goes into a queue for manual review rather than publishing automatically.</p>
    </div>

    <button type="submit">Publish to Preview</button>
  </form>
<script>
  const typeSel = document.getElementById('content_type');
  const groups = document.querySelectorAll('.field-group');
  function update() {
    const v = typeSel.value;
    groups.forEach(g => {
      g.classList.toggle('active', g.dataset.for.split(' ').includes(v));
    });
  }
  typeSel.addEventListener('change', update);
  update();
</script>
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
        content_type = request.form.get("content_type", "thought-leadership").strip()
        if content_type not in ("press", "news", "thought-leadership", "other"):
            return "Invalid content type", 400

        # Handle image upload (shared across types)
        hero_image = None
        if "image" in request.files:
            f = request.files["image"]
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                    safe_name = f"{slugify(request.form.get('headline') or request.form.get('title') or 'upload')}{ext}"
                    upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
                    os.makedirs(upload_dir, exist_ok=True)
                    f.save(os.path.join(upload_dir, safe_name))
                    hero_image = safe_name

        subs = load_submissions()

        if content_type == "thought-leadership":
            title = request.form["title"].strip()
            author = request.form["author"].strip()
            excerpt = request.form["excerpt"].strip()
            body = request.form["body"].strip()
            go_live = request.form.get("go_live", "").strip() or date.today().isoformat()
            if author not in AUTHORS:
                return "Invalid author", 400
            subs.append({
                "content_type": "thought-leadership",
                "title": title,
                "author": author,
                "excerpt": excerpt,
                "body": body,
                "go_live": go_live,
                "hero_image": hero_image,
                "submitted_at": date.today().isoformat(),
                "published": False,
            })
        elif content_type in ("press", "news"):
            headline = request.form["headline"].strip()
            publication = request.form.get("publication", "").strip() or "OneDine"
            item_date = request.form.get("item_date", "").strip() or date.today().isoformat()
            item_url = request.form.get("item_url", "").strip()
            subs.append({
                "content_type": content_type,
                "title": headline,
                "publication": publication,
                "date": item_date,
                "url": item_url,
                "hero_image": hero_image,
                "submitted_at": date.today().isoformat(),
                "published": False,
            })
        else:  # other
            other_title = request.form.get("other_title", "").strip()
            other_details = request.form.get("other_details", "").strip()
            subs.append({
                "content_type": "other",
                "title": other_title,
                "body": other_details,
                "submitted_at": date.today().isoformat(),
                "published": False,
            })
        save_submissions(subs)

        return redirect("/?success=1")

    return render_template_string(
        FORM_HTML, authors=AUTHORS, content_types=CONTENT_TYPES,
        success=request.args.get("success")
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
