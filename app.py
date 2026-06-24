import re

import requests
from feedgen.feed import FeedGenerator
from flask import Flask, Response, render_template_string, request, url_for

app = Flask(__name__)

# Public DR Lyd API key. This is shipped in DR's own web client and is not secret.
API_KEY = '6Wkh8s98Afx1ZAaTT4FuWODTmvWGDPpR'
API_BASE = 'https://api.dr.dk/radio/v2'
IMAGE_BASE = 'https://asset.dr.dk/drlyd/images'

SESSION = requests.Session()
SESSION.headers.update({'X-apikey': API_KEY})

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DR Lyd → RSS</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 4rem auto; padding: 0 1rem; }
    h1 { font-size: 1.5rem; }
    input[type=text] { width: 100%; padding: .6rem; font-size: 1rem; box-sizing: border-box; }
    button { margin-top: .8rem; padding: .6rem 1.2rem; font-size: 1rem; cursor: pointer; }
    code { background: #f0f0f0; padding: .1rem .3rem; border-radius: 3px; }
    .hint { color: #555; font-size: .9rem; }
    .err { color: #b00; }
  </style>
</head>
<body>
  <h1>DR Lyd → RSS for Audiobookshelf</h1>
  <p class="hint">Paste a DR Lyd series URL or its series id / slug.</p>
  <form action="{{ url_for('go') }}" method="get">
    <input type="text" name="series" autofocus
           placeholder="https://www.dr.dk/lyd/special-radio/hvem-bortfoerte-vores-boern-6641009937075"
           value="{{ series or '' }}">
    <button type="submit">Get RSS feed</button>
  </form>
  {% if error %}<p class="err">{{ error }}</p>{% endif %}
  {% if feed_url %}
    <p>Feed URL: <a href="{{ feed_url }}"><code>{{ feed_url }}</code></a></p>
  {% endif %}
</body>
</html>
"""


def extract_series_id(value):
    """Accept a full DR Lyd URL, a slug, or a bare production number and
    return the identifier the API expects (the slug or production number)."""
    value = (value or '').strip()
    if not value:
        return ''
    # If it's a URL, take the last non-empty path segment.
    if '/' in value:
        value = value.rstrip('/').split('/')[-1]
    # Drop any query string / fragment.
    value = re.split(r'[?#]', value)[0]
    return value


def image_url(image_assets, *targets):
    """Return the URL for the first image asset matching a preferred target."""
    by_target = {a.get('target'): a for a in image_assets or []}
    for target in targets:
        if target in by_target:
            return f"{IMAGE_BASE}/{by_target[target]['id']}"
    if image_assets:
        return f"{IMAGE_BASE}/{image_assets[0]['id']}"
    return None


def best_audio(audio_assets):
    """Pick the highest-bitrate downloadable MP3, falling back to any progressive asset."""
    progressive = [a for a in audio_assets or [] if a.get('url') and a.get('fileSize')]
    mp3s = [a for a in progressive if a.get('format', '').lower() == 'mp3']
    candidates = mp3s or progressive
    if not candidates:
        return None
    return max(candidates, key=lambda a: a.get('bitrate', 0))


def fetch_episodes(series_id):
    """Fetch all episodes for a series, following pagination."""
    items = []
    url = f"{API_BASE}/series/{series_id}/episodes/"
    while url:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items.extend(data.get('items', []))
        url = data.get('next')
    return items


def build_feed(series_id):
    episodes = fetch_episodes(series_id)
    if not episodes:
        return None

    series = episodes[0].get('series', {})
    fg = FeedGenerator()
    fg.load_extension('podcast')

    fg.id(series.get('id', f'urn:dr:radio:series:{series_id}'))
    fg.title(series.get('title', series_id))
    fg.author({'name': 'DR', 'email': 'info@dr.dk'})
    fg.language('da')
    fg.link(href=series.get('presentationUrl', f'https://www.dr.dk/lyd/{series_id}'), rel='alternate')
    fg.description(episodes[0].get('description') or f'Podcast episodes from DR Lyd: {series.get("title", series_id)}')

    cover = image_url(episodes[0].get('imageAssets'), 'Podcast', 'SquareImage', 'Default')
    if cover:
        # DR image URLs have no file extension, so feedgen's itunes_image()
        # silently drops them. The standard RSS <image> tag works fine and is
        # what Audiobookshelf reads for the cover.
        fg.logo(cover)

    for episode in episodes:
        audio = best_audio(episode.get('audioAssets'))
        if not audio:
            continue  # nothing playable; skip rather than emit a broken item
        fe = fg.add_entry()
        fe.id(episode.get('id'))
        fe.title(episode.get('title', 'Untitled'))
        fe.description(episode.get('description', ''))
        fe.enclosure(url=audio['url'], length=str(audio['fileSize']), type='audio/mpeg')
        pub = episode.get('publishTime') or episode.get('latestPublishTime')
        if pub:
            fe.pubDate(pub)
        duration = episode.get('durationMilliseconds')
        if duration:
            fe.podcast.itunes_duration(int(duration // 1000))

    return fg


@app.route('/')
def index():
    return render_template_string(INDEX_HTML, series=None, error=None, feed_url=None)


@app.route('/go')
def go():
    series_id = extract_series_id(request.args.get('series'))
    if not series_id:
        return render_template_string(
            INDEX_HTML, series=None, error='Please enter a series URL or id.', feed_url=None
        )
    feed_url = url_for('get_feed', series_id=series_id, _external=True)
    return render_template_string(
        INDEX_HTML, series=series_id, error=None, feed_url=feed_url
    )


@app.route('/feed/<path:series_id>')
def get_feed(series_id):
    series_id = extract_series_id(series_id)
    try:
        fg = build_feed(series_id)
    except requests.HTTPError as exc:
        upstream = exc.response.status_code if exc.response is not None else None
        if upstream == 404:
            return Response(f'Series "{series_id}" not found on DR.', status=404, mimetype='text/plain')
        return Response(f'DR API error for "{series_id}": {upstream}', status=502, mimetype='text/plain')
    except requests.RequestException as exc:
        return Response(f'Could not reach DR API: {exc}', status=502, mimetype='text/plain')

    if fg is None:
        return Response(f'No episodes found for series "{series_id}".', status=404, mimetype='text/plain')

    return Response(fg.rss_str(pretty=True), mimetype='application/rss+xml')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7166, debug=True)
