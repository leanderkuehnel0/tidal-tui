import requests, base64, json, mpv

def search_song(q):
    songs = requests.get(f"https://wolf.qqdl.site/search?s={q}").json()["data"]["items"]
    return songs

def play_song(id):
    manifest = requests.get(f"https://wolf.qqdl.site/track?id={id}&quality=LOSSLESS").json()["data"]["manifest"]
    url= json.loads(base64.b64decode(manifest.encode()).decode())["urls"][0]
    return url

song_id = search_song("the sound of silence simon and garfunkel")[0]
print(song_id)

song_id = song_id["id"]

print(play_song(song_id))
