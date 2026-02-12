import requests, base64, json, mpv

def search_song(q):
    songs = requests.get(f"https://wolf.qqdl.site/search?s={q}").json()["data"]["items"]
    return songs

def search_playlist(q):
    playlists = requests.get(f"https://wolf.qqdl.site/search?p={q}").json()["data"]["items"]
    return playlists

def search_artist(q):
    artists = requests.get(f"https://wolf.qqdl.site/search?a={q}").json()["data"]["artists"]["items"]
    return artists

def play_song(song_id, player):
    manifest = requests.get(f"https://wolf.qqdl.site/track?id={song_id}&quality=LOSSLESS").json()["data"]["manifest"]
    url= json.loads(base64.b64decode(manifest.encode()).decode())["urls"][0]
    player.play(url)

# The following lines are removed to make this file a module
# song_id = search_song("the sound of silence simon and garfunkel")[0]
# print(song_id)
# song_id = song_id["id"]
# print(play_song(song_id))
# input()
