#!/usr/bin/env python3
"""Search safebooru.org the way people use its site.

  booru.py tag WORD [WORD ...]
      How safebooru writes a name: matching tags with their type and post count.
  booru.py search TAG [TAG ...] [--rating general|safe|questionable|any] [--sort score|new|random]
                  [--page N] [--show N] [--sheet]
      Total posts, the tags that come up in the results (the site's sidebar), the first posts,
      and with --sheet a numbered contact sheet of them to look at in one image read.

Standard library only; --sheet needs Pillow. Sheets go to $BOORU_OUT (default: a private
booru-<uid>/ in the system's temporary folder), which keeps its 10 newest sheets.
"""
import argparse
import concurrent.futures
import html
import io
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter

SITE = 'https://safebooru.org'
API = SITE + '/index.php?page=dapi&q=index'
UA = 'sticker-box-safebooru/1.0'
BATCH = 100
# Above rating:general, posts tagged as children are always excluded, whatever the caller asks for.
CHILD_EXCLUSIONS = ['-loli', '-shota', '-child', '-aged_down', '-female_child', '-male_child']
TAG_TYPES = {0: 'general', 1: 'artist', 3: 'copyright', 4: 'character', 5: 'metadata'}
TYPE_ORDER = ['copyright', 'character', 'artist', 'general']
NOISE = re.compile(r'(^|_)commentary|^(highres|absurdres|lowres|incredibly_absurdres|bad_id|bad_pixiv_id|bad_twitter_id|'
                   r'md5_mismatch|translated|translation_request|check_translation|partially_translated|'
                   r'duplicate|resized|upscaled|third-party_edit|revision|tagme|source_request)$')
META = {'rating', 'sort', 'score', 'width', 'height', 'user', 'md5', 'id', 'parent', 'source', 'fav', 'pool', 'date'}
EXCLUDE_MARK = '\u2212'
UID = os.getuid() if hasattr(os, 'getuid') else None
SHEET_DIR = os.environ.get('BOORU_OUT') or os.path.join(tempfile.gettempdir(), 'booru' if UID is None else f'booru-{UID}')
SHEET_NAME = re.compile(r'^\d{8}-\d{6}-[0-9A-Za-z_-]*\.jpg$')
KEEP_SHEETS = 10


class Refused(Exception):
    pass


def get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise Refused(f'HTTP {e.code}') from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise Refused(str(getattr(e, 'reason', e))) from None


def q(tags) -> str:
    return '+'.join(urllib.parse.quote(t, safe=':()!\'') for t in tags)


def autocomplete(word: str) -> list[tuple[str, int]]:
    """The 10 most used tags starting with word; [] when the site does not answer."""
    try:
        data = json.loads(get(f'{SITE}/autocomplete.php?q={urllib.parse.quote(word)}', 15) or b'[]')
    except (Refused, ValueError):
        return []
    out = []
    for item in data:
        m = re.search(r'\((\d+)\)\s*$', item.get('label', ''))
        out.append((html.unescape(item.get('value', '')), int(m.group(1)) if m else 0))
    return out


def tag_pattern(pattern: str) -> dict[str, tuple[str, int]] | None:
    """Tags matching a LIKE pattern, with type and post count; None when the site does not answer."""
    try:
        xml = get(f'{API}&s=tag&limit=1000&name_pattern={urllib.parse.quote(pattern)}', 20).decode('utf-8', 'replace')
    except Refused:
        return None
    found = {}
    for m in re.finditer(r'<tag type="(\d+)" count="(\d+)" name="([^"]*)"', xml):
        found[html.unescape(m.group(3))] = (TAG_TYPES.get(int(m.group(1)), '?'), int(m.group(2)))
    return found


def cmd_tag(words: list[str]) -> None:
    word = '_'.join(w.strip().lower().replace(' ', '_') for w in words if w.strip())
    if not word:
        sys.exit('give a name, e.g. booru.py tag perlica')
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        ac = ex.submit(autocomplete, word)
        pat = ex.submit(tag_pattern, '%' + word.replace('_', '%') + '%')
        prefix, contains = ac.result(), pat.result()
    merged = dict(contains or {})
    for name, count in prefix:
        kind = merged.get(name, ('?', 0))[0]
        merged[name] = (kind, max(count, merged.get(name, ('?', 0))[1]))
    rows = sorted(merged.items(), key=lambda kv: -kv[1][1])[:15]
    if not rows:
        print(f'No tag contains "{word}". safebooru tags are English or romaji with _ for spaces, character tags often end in'
              f' _(series). Try another spelling, or web-search "<name> danbooru tag".')
        return
    print(f'Tags containing "{word}", most posts first:')
    for name, (kind, count) in rows:
        print(f'  {name}  [{kind}]  {count} posts')


def split_query(raw: list[str], rating: str | None):
    tags, ratings, sort = [], [], None
    for t in ' '.join(raw).split():
        low = t.lower().replace(EXCLUDE_MARK, '-')
        if low.startswith('rating:'):
            ratings.append(low.split(':', 1)[1])
        elif low.startswith('sort:'):
            sort = low
        else:
            tags.append(low)
    rating = (rating or (ratings[-1] if ratings else 'general')).lower()
    if rating not in ('general', 'safe', 'questionable', 'any'):
        sys.exit(f'unknown rating {rating}: use general, safe, questionable or any')
    return tags, rating, sort


def sidebar(page_html: str) -> dict[str, tuple[str, int]]:
    found = {}
    for m in re.finditer(r'<li class="tag-type-(\w+)">.*?page=post&s=list&tags=([^"]+)">.*?'
                         r'<span class="tag-count">\s*(\d+)', page_html, re.S):
        found[html.unescape(urllib.parse.unquote_plus(m.group(2)))] = (m.group(1), int(m.group(3)))
    return found


def cmd_search(a) -> None:
    tags, rating, sort_tag = split_query(a.tags, a.rating)
    if not tags:
        sys.exit('give at least one tag, e.g. booru.py search perlica_(arknights)')
    sort_tag = {'score': 'sort:score', 'new': None, 'random': 'sort:random'}[a.sort] if a.sort else sort_tag or 'sort:score'
    full = list(tags)
    if rating != 'any':
        full.append('rating:' + rating)
    if rating != 'general':
        full += [x for x in CHILD_EXCLUSIONS if x not in full]
    listed = full + ([sort_tag] if sort_tag else [])
    positive = [t for t in tags if not t.startswith(('-', '~')) and t.split(':', 1)[0] not in META]

    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        f_count = ex.submit(get, f'{API}&s=post&limit=0&tags={q(full)}', 20)
        f_posts = ex.submit(get, f'{API}&s=post&json=1&limit={BATCH}&pid={a.page}&tags={q(listed)}', 25)
        f_page = ex.submit(get, f'{SITE}/index.php?page=post&s=list&pid={a.page * BATCH}&tags={q(listed)}', 25)
        f_exact = {t: ex.submit(tag_pattern, t) for t in positive}
        try:
            m = re.search(rb'count="(\d+)"', f_count.result())
            total = int(m.group(1)) if m else None
            body = f_posts.result().strip()
            posts = json.loads(body) if body else []
        except (Refused, ValueError) as e:
            sys.exit(f'safebooru did not answer ({e}). Wait a minute and try again; do not hammer it.')
        try:
            side = sidebar(f_page.result().decode('utf-8', 'replace'))
        except Refused:
            side = {}
        exact = {t: f.result() for t, f in f_exact.items()}

    print(f'search: {" ".join(listed)}')
    print(f'total: {total if total is not None else "?"} posts')
    for t in positive:
        if exact[t] is None:
            continue
        count = exact[t].get(t.lower(), (None, None))[1]
        if count is not None and count >= 50:
            continue
        alt = ', '.join(f'{n} ({c})' for n, c in autocomplete(t)[:6] if n != t.lower())
        if count is None:
            print(f'  ! "{t}" is not a tag on safebooru. {("Similar: " + alt) if alt else "Look it up: booru.py tag " + t}')
        else:
            print(f'  ! "{t}" has only {count} posts on the whole site; probably not the tag you mean.'
                  f'{(" Similar: " + alt) if alt else ""}')
    if not posts:
        print('No posts. Every tag must match at once (space means AND), so one wrong or too narrow tag empties the'
              ' search. Drop or replace the last tag, or check the spellings with booru.py tag.')
        return

    # The site's own sidebar covers only some of the page's tags, so it is used for types and site totals,
    # never to decide which tags to list.
    counts = Counter(t for p in posts for t in set(p.get('tags', '').split()))
    query_set = {t.lower() for t in tags}
    groups: dict[str, list[str]] = {k: [] for k in TYPE_ORDER}
    for tag, n in counts.most_common():
        tag = html.unescape(tag)
        if tag.lower() in query_set or NOISE.search(tag):
            continue
        kind, site_count = side.get(tag, ('general', None))
        if kind not in groups:
            continue
        if len(groups[kind]) < (30 if kind == 'general' else 8):
            share = round(100 * n / len(posts))
            groups[kind].append(f'{tag} {share}%' + (f' ({site_count})' if site_count is not None else ''))
    print(f'\nrelated tags: share of these {len(posts)} posts, then (posts on the whole site) when known')
    for kind in TYPE_ORDER:
        if groups[kind]:
            print(f'  {kind}: ' + ', '.join(groups[kind]))

    shown = posts[:a.show]
    print(f'\nposts {a.page * BATCH + 1}-{a.page * BATCH + len(shown)} (page: {SITE}/index.php?page=post&s=view&id=<id>):')
    for i, p in enumerate(shown, 1):
        chars = [t for t in p.get('tags', '').split() if side.get(html.unescape(t), ('',))[0] == 'character']
        url = p.get('sample_url') if p.get('sample') else p.get('file_url')
        print(f'  #{i} id {p["id"]}  {p.get("rating")}  score {p.get("score")}  {p.get("width")}x{p.get("height")}'
              f'{"  " + " ".join(chars) if chars else ""}\n      {url}'
              f'{chr(10) + "      source: " + p["source"] if p.get("source") else ""}')
    if len(posts) > a.show:
        print(f'  (more: --show {min(len(posts), a.show * 2)}, or --page {a.page + 1} for the next {BATCH})')
    if a.sheet:
        print('\nsheet: ' + make_sheet(shown, tags))


def make_sheet(posts, tags) -> str:
    from PIL import Image, ImageDraw, ImageFont

    def fetch(p):
        try:
            img = Image.open(io.BytesIO(get(p.get('preview_url') or p['sample_url'], 15)))
            img.seek(0)
            return img.convert('RGB')
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(6) as ex:
        images = list(ex.map(fetch, posts))
    cell, cols = 250, 4
    rows = (len(posts) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rows * cell), 'white')
    draw = ImageDraw.Draw(sheet)
    font = None
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',):
        if os.path.exists(path):
            font = ImageFont.truetype(path, 26)
            break
    if font is None:
        try:
            font = ImageFont.load_default(size=26)
        except TypeError:
            font = ImageFont.load_default()
    for i, img in enumerate(images):
        x, y = (i % cols) * cell, (i // cols) * cell
        if img is None:
            draw.text((x + 80, y + 110), 'failed', fill='red', font=font)
        else:
            img.thumbnail((cell - 6, cell - 6))
            sheet.paste(img, (x + (cell - img.width) // 2, y + (cell - img.height) // 2))
        label = f'#{i + 1}'
        box = draw.textbbox((x + 4, y + 4), label, font=font)
        draw.rectangle((box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3), fill='#ffe9a8')
        draw.text((x + 4, y + 4), label, fill='black', font=font)
    os.makedirs(SHEET_DIR, mode=0o700, exist_ok=True)
    if UID is not None and 'BOORU_OUT' not in os.environ:
        st = os.lstat(SHEET_DIR)
        if not os.path.isdir(SHEET_DIR) or os.path.islink(SHEET_DIR) or st.st_uid != UID:
            sys.exit(f'{SHEET_DIR} is not a folder of yours; set BOORU_OUT to one')
    slug = re.sub(r'[^0-9A-Za-z_]+', '-', '_'.join(t for t in tags if not t.startswith('-')))[:40].strip('-') or 'search'
    path = os.path.join(SHEET_DIR, f'{time.strftime("%Y%m%d-%H%M%S")}-{slug}.jpg')
    sheet.save(path, quality=85)
    old = sorted((f for f in os.listdir(SHEET_DIR) if SHEET_NAME.match(f)), reverse=True)[KEEP_SHEETS:]
    for f in old:
        os.remove(os.path.join(SHEET_DIR, f))
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('tag')
    t.add_argument('words', nargs='+')
    s = sub.add_parser('search')
    s.add_argument('tags', nargs='+')
    s.add_argument('--rating', choices=['general', 'safe', 'questionable', 'any'])
    s.add_argument('--sort', choices=['score', 'new', 'random'])
    s.add_argument('--page', type=int, default=0)
    s.add_argument('--show', type=int, default=12)
    s.add_argument('--sheet', action='store_true')
    # A single-dash word is an excluded tag (-comic), not an option.
    argv = [EXCLUDE_MARK + x[1:] if x.startswith('-') and not x.startswith('--') and x != '-h' else x for x in sys.argv[1:]]
    a = p.parse_args(argv)
    if a.cmd == 'tag':
        cmd_tag(a.words)
    else:
        a.show = max(1, min(a.show, 24))
        cmd_search(a)


if __name__ == '__main__':
    main()
