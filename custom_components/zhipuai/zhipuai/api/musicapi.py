import random, json, asyncio, aiohttp, base64, urllib3, tempfile, os, shutil
from Crypto.Cipher import AES
import aiofiles
from functools import partial

try:
    from mutagen.mp3 import MP3
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KEY = '0CoJUm6Qyw8W8jud'
F = '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7'
E = '010001'

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36', 'Referer': 'https://music.163.com/', 'Origin': 'https://music.163.com', 'Accept': 'application/json, text/plain, */*', 'Content-Type': 'application/x-www-form-urlencoded'}

TOUBIEC_API_URL = 'https://api.toubiec.cn/api/music_v1.php'
TOUBIEC_API_TOKEN = '5adff316e25f46d5d9208e43a5787f25'
TOUBIEC_API_HEADERS = {'accept': 'application/json, text/plain, */*', 'accept-language': 'en,zh-CN;q=0.9,zh-TW;q=0.8,zh;q=0.7', 'authorization': 'Bearer 18e30d8eb0805e792e364e073f292322', 'content-type': 'application/json', 'origin': 'https://api.toubiec.cn', 'referer': 'https://api.toubiec.cn/wyapi.html', 'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'}

def generate_random_str(length):
    return "".join(random.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(length))

def aes_encrypt(text, key):
    pad = 16 - len(text) % 16
    text = text + chr(pad) * pad
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, '0102030405060708'.encode('utf-8'))
    return base64.b64encode(cipher.encrypt(text.encode('utf-8'))).decode('utf-8')

def rsa_encrypt(text, key, f):
    return format(pow(int(text[::-1].encode('utf-8').hex(), 16), int(key, 16), int(f, 16)), 'x').zfill(256)

def get_encrypted_params(song_id):
    msg = f'{{"ids": "[{song_id}]", "level": "standard", "encodeType": "mp3", "csrf_token": ""}}'
    first_enc = aes_encrypt(msg, KEY)
    random_str = generate_random_str(16)
    return aes_encrypt(first_enc, random_str), rsa_encrypt(random_str, E, F)

async def async_get_song_id(query, prefer_non_vip=False):
    search_url = "https://music.163.com/api/search/get/web"
    params = {'s': query, 'type': 1, 'limit': 20, 'offset': 0}
    artist_query = None
    song_query = query
    
    if " - " in query:
        song_query, artist_query = [p.strip() for p in query.split(" - ", 1)]
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(search_url, params=params, headers=HEADERS, ssl=False) as response:
                result = await response.json()
                if 'result' in result and 'songs' in result['result'] and result['result']['songs']:
                    songs = result['result']['songs']
                    scored_songs = []
                    
                    for song in songs:
                        song_name = song.get('name', '')
                        artist_names = [artist.get('name', '') for artist in song.get('artists', [])]
                        is_vip = song.get('fee', 0) == 1
                        score = 0
                        
                        if song_name.lower() == song_query.lower(): score += 100
                        elif song_name.lower().startswith(song_query.lower()): score += 80
                        elif song_query.lower() in song_name.lower(): score += 60
                        
                        if artist_query:
                            artist_score = max([100 if artist.lower() == artist_query.lower() else 80 if artist_query.lower() in artist.lower() else 60 if artist.lower() in artist_query.lower() else 0 for artist in artist_names])
                            score += artist_score
                        
                        if song.get('sq'): score += 15
                        elif song.get('h'): score += 10
                        if prefer_non_vip and not is_vip: score += 5
                        
                        scored_songs.append((song, score))
                    
                    scored_songs.sort(key=lambda x: x[1], reverse=True)
                    return scored_songs[0][0]['id'] if scored_songs else None
    except Exception:
        return None

async def async_get_mp3_url_advanced(song_id):
    try:
        payload = {"url": f"https://music.163.com/#/song?id={song_id}", "level": "exhigh", "type": "song", "token": TOUBIEC_API_TOKEN}
        async with aiohttp.ClientSession() as session:
            async with session.post(TOUBIEC_API_URL, json=payload, headers=TOUBIEC_API_HEADERS) as response:
                result = await response.json()
                if result.get('status') == 200:
                    return {
                        "url": result.get('url_info', {}).get('url', ''),
                        "song_info": {
                            "name": result.get('song_info', {}).get('name', ''),
                            "artist": result.get('song_info', {}).get('artist', ''),
                            "album": result.get('song_info', {}).get('album', ''),
                            "cover": result.get('song_info', {}).get('cover', '')
                        },
                        "lrc": result.get('lrc', {}).get('lyric', '')
                    }
    except Exception:
        pass
    return {"url": f'http://music.163.com/song/media/outer/url?id={song_id}.mp3', "song_info": {}, "lrc": ""}

async def async_get_mp3_url(song_id):
    try:
        params, encSecKey = get_encrypted_params(song_id)
        async with aiohttp.ClientSession() as session:
            async with session.post('https://music.163.com/weapi/song/enhance/player/url/v1?csrf_token=', data={'params': params, 'encSecKey': encSecKey}, headers=HEADERS, ssl=False) as response:
                result = await response.json()
                if result.get('data') and result['data'] and result['data'][0].get('url'):
                    return {"url": result['data'][0]['url'], "song_info": {}, "lrc": ""}
    except Exception:
        pass
    return await async_get_mp3_url_advanced(song_id)

async def async_get_song_duration(url):
    if not HAS_MUTAGEN:
        return 0
        
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, "temp_song.mp3")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, ssl=False) as response:
                if response.status != 200:
                    return 0
                    
                async with aiofiles.open(temp_file, 'wb') as f:
                    await f.write(await response.read())
        
        loop = asyncio.get_event_loop()
        duration = await loop.run_in_executor(None, lambda: int(MP3(temp_file).info.length))
        
        return duration
    except Exception:
        return 0
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                await asyncio.get_event_loop().run_in_executor(None, shutil.rmtree, temp_dir)
            except Exception:
                pass

async def async_search_song(query, prefer_non_vip=False):
    song_id = await async_get_song_id(query, prefer_non_vip)
    if song_id:
        try:
            payload = {"url": f"https://music.163.com/#/song?id={song_id}", "level": "exhigh", "type": "song", "token": TOUBIEC_API_TOKEN}
            async with aiohttp.ClientSession() as session:
                async with session.post(TOUBIEC_API_URL, json=payload, headers=TOUBIEC_API_HEADERS) as response:
                    result = await response.json()
                    if result.get('status') == 200:
                        song_url = result['url_info']['url']
                        song_info = result['song_info']
                        song_info['duration'] = await async_get_song_duration(song_url)
                        return {"success": True, "url": song_url, "song_id": song_id, "song_info": song_info}
        except Exception:
            pass
    return {"success": False, "message": f"未找到歌曲: {query}"}

def search_song(query):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(async_search_song(query)) if not loop.is_running() else {"success": False, "message": "不能在事件循环中同步调用"}

async def async_get_playlist_songs(playlist_id):
    try:
        payload = {"url": f"https://music.163.com/#/playlist?id={playlist_id}", "type": "playlist", "token": TOUBIEC_API_TOKEN}
        async with aiohttp.ClientSession() as session:
            async with session.post(TOUBIEC_API_URL, json=payload, headers=TOUBIEC_API_HEADERS) as response:
                result = await response.json()
                if result.get('status') == 200 and 'playlist' in result:
                    tracks = result.get('playlist', {}).get('tracks', [])
                    return {
                        "success": True,
                        "playlist_name": result.get('playlist', {}).get('name', ''),
                        "songs": [{
                            "id": track.get('id'),
                            "name": track.get('name', ''),
                            "artist": track.get('ar', [{}])[0].get('name', ''),
                            "album": track.get('al', {}).get('name', ''),
                            "cover": track.get('al', {}).get('picUrl', '')
                        } for track in tracks]
                    }
    except Exception as e:
        return {"success": False, "message": f"处理播放列表时出错: {str(e)}"}
    return {"success": False, "message": f"获取播放列表失败: {playlist_id}"}