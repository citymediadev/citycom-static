#!/usr/bin/env python3
"""Post-export speed fixes for the static Elementor site.

Runs on every Cloudflare Pages build (and can be run locally), so the fixes
survive a fresh export from WordPress/Elementor. Safe to run repeatedly.

1. Page header background images -> resized WebP + high-priority preload.
2. Hosted background videos -> 1080p fast-start MP4 + poster, played directly
   (not via Elementor's script, which restarts and resizes the video).
3. Long-lived cache headers for static assets (_headers).

Generated files are named after a hash of their source, so they are only
rebuilt when the source image/video changes. Commit them to keep builds fast.
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'.git', 'tools', 'wp-content', 'wp-includes', 'wp-admin', 'elementor-hf'}
MARK = 'data-citycom-opt'

DESKTOP_WIDTH = 1920
MOBILE_WIDTH = 1080
WEBP_QUALITY = 82

HEADERS = """/wp-content/*
  Cache-Control: public, max-age=31536000, immutable

/wp-includes/*
  Cache-Control: public, max-age=31536000, immutable
"""

VIDEO_CSS = ('<style %s>.citycom-hero-video{position:absolute;inset:0;width:100%%;'
             'height:100%%;object-fit:cover}</style>' % MARK)


def short_hash(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:8]


def local_path(url):
    return os.path.join(ROOT, url.lstrip('/'))


def ffmpeg():
    exe = os.environ.get('FFMPEG') or shutil.which('ffmpeg')
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def make_webp(url, width):
    src = local_path(url)
    stem, _ = os.path.splitext(url)
    out = f'{stem}.{short_hash(src)}.w{width}.webp'
    if not os.path.exists(local_path(out)):
        from PIL import Image
        img = Image.open(src)
        img = img.convert('RGBA' if img.mode in ('RGBA', 'LA', 'P') else 'RGB')
        if img.width > width:
            img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
        img.save(local_path(out), 'WEBP', quality=WEBP_QUALITY, method=6)
        print(f'  image  {url} -> {out}')
    return out


def make_video(url, start):
    src = local_path(url)
    stem, _ = os.path.splitext(url)
    h = short_hash(src)
    out, poster = f'{stem}.{h}.mp4', f'{stem}.{h}.poster.jpg'
    ff = ffmpeg() if not (os.path.exists(local_path(out)) and os.path.exists(local_path(poster))) else None
    if not os.path.exists(local_path(out)):
        subprocess.run([ff, '-hide_banner', '-loglevel', 'error', '-y', '-i', src,
                        '-vf', "scale='min(1920,iw)':-2:flags=lanczos", '-c:v', 'libx264',
                        '-preset', 'slow', '-crf', '22', '-maxrate', '2M', '-bufsize', '4M',
                        '-pix_fmt', 'yuv420p', '-an', '-movflags', '+faststart',
                        local_path(out)], check=True)
        print(f'  video  {url} -> {out}')
    if not os.path.exists(local_path(poster)):
        subprocess.run([ff, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(start),
                        '-i', src, '-frames:v', '1', '-vf', "scale='min(1920,iw)':-2",
                        '-q:v', '3', local_path(poster)], check=True)
    return out, poster


def in_mobile_query(s, pos):
    """True if the CSS at pos sits inside an @media(max-width:767px) block."""
    k = s.rfind('@media', 0, pos)
    return k > s.rfind('}}', 0, pos) and 'max-width:767px' in s[k:k + 30]


def fix_header_image(s):
    i = s.find('data-elementor-type="wp-page"')
    m = i >= 0 and re.search(r'data-id="([0-9a-f]+)"', s[i:])
    if not m:
        return s, ''
    pat = re.compile(r'(elementor-element-' + m.group(1) +
                     r'[^{}]*\{[^{}]*background-image:url\("?)(/wp-content/[^")]+\.(?:jpe?g|png))("?\))', re.I)
    chosen = {}

    def rep(mm):
        if not os.path.exists(local_path(mm.group(2))):
            return mm.group(0)
        mobile = in_mobile_query(s, mm.start())
        new = make_webp(mm.group(2), MOBILE_WIDTH if mobile else DESKTOP_WIDTH)
        if mobile or s.rfind('@media', 0, mm.start()) <= s.rfind('}}', 0, mm.start()):
            chosen.setdefault('m' if mobile else 'd', new)
        return mm.group(1) + new + mm.group(3)

    s = pat.sub(rep, s)
    links = ''
    if 'd' in chosen:
        media = ' media="(min-width: 768px)"' if 'm' in chosen else ''
        links += f'<link rel="preload" as="image" href="{chosen["d"]}" fetchpriority="high"{media} {MARK}>\n'
    if 'm' in chosen:
        links += f'<link rel="preload" as="image" href="{chosen["m"]}" fetchpriority="high" media="(max-width: 767px)" {MARK}>\n'
    return s, links


def fix_background_video(s):
    tag = re.search(r'<video class="elementor-background-video-hosted"[^>]*></video>', s)
    if not tag:
        return s, ''
    ds = s.rfind('data-settings="', 0, tag.start())
    if ds < 0:
        return s, ''
    ds += len('data-settings="')
    settings = json.loads(html.unescape(s[ds:s.find('"', ds)]))
    url = settings.get('background_video_link', '')
    if not url.startswith('/wp-content/') or not os.path.exists(local_path(url)):
        return s, ''
    start = settings.get('background_video_start') or 0
    out, poster = make_video(url, start)
    frag = f'#t={start}' if start else ''
    video = (f'<video class="citycom-hero-video" role="presentation" autoplay muted playsinline loop '
             f'preload="auto" poster="{poster}" src="{out}{frag}"></video>')
    return s[:tag.start()] + video + s[tag.end():], VIDEO_CSS + '\n'


def process(path):
    s = open(path, encoding='utf-8').read()
    if MARK in s:
        return False
    s, links = fix_header_image(s)
    s, css = fix_background_video(s)
    if not (links or css):
        return False
    s = re.sub(r'(<head[^>]*>)', lambda m: m.group(1) + '\n' + links + css, s, count=1)
    open(path, 'w', encoding='utf-8').write(s)
    return True


def main():
    changed = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if 'index.html' in filenames:
            path = os.path.join(dirpath, 'index.html')
            if process(path):
                changed += 1
                print('optimised', os.path.relpath(path, ROOT))
    with open(os.path.join(ROOT, '_headers'), 'w') as f:
        f.write(HEADERS)
    print(f'done: {changed} page(s) updated')


if __name__ == '__main__':
    sys.exit(main())
