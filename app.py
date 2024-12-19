from flask import Flask, Response
from feedgen.feed import FeedGenerator
import requests

app = Flask(__name__)

@app.route('/feed/<series_id>')
def get_feed(series_id):
    fg = FeedGenerator()
   
    # Fetch episodes
    headers = {
        'X-apikey': '6Wkh8s98Afx1ZAaTT4FuWODTmvWGDPpR'
    }
    response = requests.get(f'https://api.dr.dk/radio/v2/series/' + series_id +'/episodes/', headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        fg.id(f'urn:uuid:{series_id}')
        fg.title(result['items'][0]['series']['title'])
        fg.author({'name': 'DR', 'email': 'info@dr.dk'})
        fg.link(href=f'https://api.dr.dk/radio/v2/series/{series_id}/episodes/', rel='alternate')
        fg.description('Podcast episodes from DR.dk')
 
        episodes = result['items']
        for episode in episodes:
            fe = fg.add_entry()
            fe.id(episode['id'])
            fe.title(episode['title'])
            fe.link(href=episode['audioAssets'][4]['url'])
            fe.description(episode.get('description', ''))
            fe.pubDate(episode.get('latestPublishTime', ''))
            
    rssfeed = fg.rss_str(pretty=True)
    return Response(rssfeed, mimetype='application/rss+xml')

if __name__ == '__main__':
    app.run(debug=True)
