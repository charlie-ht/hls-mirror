#!/usr/bin/python3

import m3u8
import fileinput
import re
import requests
from urllib.parse import urlparse
from urllib.parse import urljoin
from pathlib import Path
import shutil
from hashlib import sha256
import os
import argparse

seen_medias = set()
downloaded_uris = dict()
range_re = re.compile('bytes (?P<start>\d+)-(?P<end>\d+)\/(?P<total_size>\d+)')
playlist_basepath = None

SCRIPTDIR = os.path.normpath(os.path.dirname(__file__))

def uri_is_absolute(uri):
    return bool(urlparse(uri).netloc)


def uri_basename(uri):
    parsed_uri = urlparse(uri)
    return Path(parsed_uri.path).name


def download_uri(uri, local_file_name):
    if uri in downloaded_uris:
        return downloaded_uris[uri]

    parsed_uri = urlparse(uri)
    if parsed_uri.query:
        # This helps keep the downloaded files unique and non-colliding.
        local_file_name = sha256(parsed_uri.query.encode('utf-8')).hexdigest() + '-' + local_file_name

    with requests.get(uri, stream=True) as r:
        if 'Content-Range' in r.headers:
            match = re.match(range_re, r.headers['Content-Range'])
            if match:
                (start, end, _) = match.groups()
                local_file_name = f'ranged-{start}-{end}-{local_file_name}'

        with open(local_file_name, 'wb') as f:
            shutil.copyfileobj(r.raw, f)

        downloaded_uris[uri] = local_file_name
        return local_file_name


def localize(playlist_uri):
    if not uri_is_absolute(playlist_uri):
        playlist_uri = urljoin(playlist_basepath, playlist_uri)

    print(f'loading {playlist_uri}')
    m3u8_obj = m3u8.load(playlist_uri)

    if m3u8_obj.is_variant:
        for playlist in m3u8_obj.playlists:
            localized_file_name = localize(playlist.uri)
            print(f'playlist: {playlist.uri} ... {localized_file_name}')
            playlist.uri = localized_file_name

            for media in playlist.media:
                if media not in seen_medias:
                    seen_medias.add(media)
                    localized_media_uri = localize(media.uri)
                    print(f'media: {media.uri} ... {localized_media_uri}')
                    media.uri = localized_media_uri


        for iframe_playlist in m3u8_obj.iframe_playlists:
            localized_file_name = localize(iframe_playlist.uri)
            print(f'iframe: {iframe_playlist.uri} ... {localized_file_name}')
            iframe_playlist.uri = localized_file_name

    else:
        for segment in m3u8_obj.segments:
            segment_absolute_uri = urljoin(m3u8_obj.base_uri, segment.uri)
            segment_uri_basename = uri_basename(segment_absolute_uri)
            saved_as = download_uri(segment_absolute_uri, segment_uri_basename)
            print(f'segment: {segment.uri} ... {saved_as}')
            segment.uri = saved_as

    localized_playlist_uri = uri_basename(playlist_uri)
    m3u8_obj.dump(localized_playlist_uri)
    return localized_playlist_uri 


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog="hls-mirror")

    parser.add_argument('playlist_uri', metavar='playlist_uri', type=str,
                        help='The URI of the master playlist to mirror locally')

    options = parser.parse_args()

    playlist_basepath, _ = os.path.split(options.playlist_uri)
    playlist_basepath += '/'

    localize(options.playlist_uri)

