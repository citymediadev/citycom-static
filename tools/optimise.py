#!/usr/bin/env python3
"""Post-export speed fixes for the static Elementor site.

Runs on every Cloudflare Pages build (and can be run locally), so the fixes
survive a fresh export from WordPress/Elementor. Safe to run repeatedly.

1. Page header background images -> resized WebP + high-priority preload.
2. Hosted background videos -> 1080p fast-start MP4 + poster, played directly
   (not via Elementor's script, which restarts and resizes the video).
3. Long-lived cache headers for static assets (_headers).
4. Fluent Forms -> Web3Forms, so the contact form works without WordPress.

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

# Simply Static exports absolute URLs on the live domain; asset URLs may carry it.
SITE = 'https://citycomuk.com'
SITE_RE = r'(?:https?://(?:www\.)?citycomuk\.com)?'

DESKTOP_WIDTH = 1920
MOBILE_WIDTH = 1080
WEBP_QUALITY = 82

HEADERS = """/*
  Strict-Transport-Security: max-age=31536000
  X-Frame-Options: SAMEORIGIN
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin

https://:project.pages.dev/*
  X-Robots-Tag: noindex

/wp-content/*
  Cache-Control: public, max-age=31536000, immutable

/wp-includes/*
  Cache-Control: public, max-age=31536000, immutable
"""

VIDEO_CSS = ('<style %s>.citycom-hero-video{position:absolute;inset:0;width:100%%;'
             'height:100%%;object-fit:cover}</style>' % MARK)

# Fluent Forms needs WordPress to submit, so forms are sent to Web3Forms instead.
WEB3FORMS_KEY = '78ea0c8b-62a1-4bca-9b73-da5446b9d26a'
FORM_SUBJECT = 'New enquiry from the Citycom website'
FIELD_NAMES = {'names[first_name]': 'Name', 'input_text': 'Phone', 'message': 'Message'}
FORM_HIDDEN = (
    f'<input type="hidden" name="access_key" value="{WEB3FORMS_KEY}">'
    f'<input type="hidden" name="subject" value="{FORM_SUBJECT}">'
    '<input type="hidden" name="from_name" value="Citycom website">'
    '<input type="checkbox" name="botcheck" style="display:none" tabindex="-1" autocomplete="off">'
)
FORM_JS = '''<style %(m)s>.citycom-form-msg{margin-top:12px;font-weight:500}</style>
<script %(m)s>
document.addEventListener('submit', function (e) {
  var form = e.target;
  if (!form.classList || !form.classList.contains('citycom-web3form')) return;
  e.preventDefault();
  var btn = form.querySelector('[type=submit]'), label = btn.textContent;
  var msg = form.parentNode.querySelector('.citycom-form-msg');
  if (!msg) {
    msg = document.createElement('div');
    msg.className = 'citycom-form-msg';
    msg.setAttribute('role', 'status');
    form.after(msg);
  }
  btn.disabled = true;
  btn.textContent = 'Sending...';
  msg.textContent = '';
  fetch(form.action, {method: 'POST', body: new FormData(form), headers: {Accept: 'application/json'}})
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.success) throw new Error(d.message);
      form.reset();
      msg.textContent = "Thanks, your message has been sent. We'll be in touch soon.";
    })
    .catch(function () {
      msg.textContent = 'Sorry, your message could not be sent. Please try again, or contact us by phone or email.';
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = label;
    });
});
</script>
''' % {'m': MARK}


def short_hash(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:8]


def site_path(url):
    """'https://citycomuk.com/wp-content/x.jpg' -> '/wp-content/x.jpg'."""
    return re.sub('^' + SITE_RE, '', url)


def local_path(url):
    return os.path.join(ROOT, site_path(url).lstrip('/'))


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
                     r'[^{}]*\{[^{}]*background-image:url\("?)' + SITE_RE +
                     r'(/wp-content/[^")]+\.(?:jpe?g|png))("?\))', re.I)
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
    url = site_path(settings.get('background_video_link', ''))
    if not url.startswith('/wp-content/') or not os.path.exists(local_path(url)):
        return s, ''
    start = settings.get('background_video_start') or 0
    out, poster = make_video(url, start)
    frag = f'#t={start}' if start else ''
    video = (f'<video class="citycom-hero-video" role="presentation" autoplay muted playsinline loop '
             f'preload="auto" poster="{poster}" src="{out}{frag}"></video>')
    return s[:tag.start()] + video + s[tag.end():], VIDEO_CSS + '\n'


def fix_forms(s):
    def open_tag(m):
        cls = re.search(r'class="([^"]*)"', m.group(0)).group(1).split()
        cls = [c for c in cls if c not in ('frm-fluent-form', 'ff-form-loading', 'ff_has_v3_recptcha')]
        return (f'<form class="{" ".join(cls)} citycom-web3form" '
                f'action="https://api.web3forms.com/submit" method="POST">' + FORM_HIDDEN)

    def rep(m):
        f = re.sub(r'^<form[^>]*>', open_tag, m.group(0))
        f = re.sub(r'<input type="hidden"[^>]*name="(?:__fluent_form_embded_post_id|_wp_http_referer|'
                   r'_fluentform_\d+_fluentformnonce)"[^>]*>', '', f)
        for old, new in FIELD_NAMES.items():
            f = f.replace(f'name="{old}"', f'name="{new}"')
        return re.sub(r'(<(?:input|textarea)\b[^>]*aria-required="true")', r'\1 required', f)

    s, n = re.subn(r'<form\b[^>]*class="frm-fluent-form[^"]*"[^>]*>.*?</form>', rep, s, flags=re.S)
    if not n:
        return s, ''
    # Fluent's own script would hijack the submit and post to WordPress.
    s = re.sub(r'<script id="fluent-form-submission-js"[^>]*></script>', '', s)
    return s, FORM_JS


def process(path):
    s = open(path, encoding='utf-8').read()
    # Each fix only matches untouched export markup, so re-running is a no-op.
    s, links = fix_header_image(s)
    s, css = fix_background_video(s)
    s, form_js = fix_forms(s)
    if not (links or css or form_js):
        return False
    s = re.sub(r'(<head[^>]*>)', lambda m: m.group(1) + '\n' + links + css + form_js, s, count=1)
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
    # On Cloudflare Pages the repo root is the published site; keep this script out of it.
    if os.environ.get('CF_PAGES'):
        shutil.rmtree(os.path.join(ROOT, 'tools'), ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
