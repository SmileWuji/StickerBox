---
name: safebooru
description: Search safebooru.org for anime-style pictures by tag. Use to see what a character looks like, to find how a name is written as a tag there, to find pictures of a character, work or theme, or to follow a post's source to where a picture came from.
---

# Searching safebooru

safebooru.org is an image board without adult content. Most of its pictures and tags come from
Danbooru, and each post carries its original source (`source`, mostly pixiv or X). The script is
in this skill's folder:

```
python3 <this skill's folder>/booru.py tag <name>
python3 <this skill's folder>/booru.py search <tag> [<tag> ...] [--sheet]
```

`tag` and `search` need only the standard library. `--sheet` needs Pillow; the sheet is written
to `$BOORU_OUT` (by default a private `booru-<uid>/` in the system's temporary folder) and its path is printed on
the last line, so look at it there. safebooru.donmai.us is blocked by Cloudflare; do not use it.

## Tags are not keywords

- Every tag has one fixed spelling, in English or romanised Japanese, with `_` for spaces:
  `white_hair`, `komeiji_koishi`.
- Character tags often end in the work's name: `perlica_(arknights)`.
- A space between tags means AND. `perlica arknights` asks for posts carrying both the tag
  `perlica` and the tag `arknights`, and finds 2; `perlica_(arknights)` has 1336. **Few results
  usually mean a wrong tag, not few pictures.**
- `-tag` excludes, e.g. `-comic`.
- The site has no Chinese tags. Turn a Chinese name or a nickname into the official romanised or
  English name first; if none comes to mind, web-search "<name> danbooru".
- When turning a description into tags, think of two or three near ones: smiling can be
  `smile`, `grin` or `:d`; sleeping can be `sleeping`, `closed_eyes` or `lying`.

## Narrow down the way a person uses the site

A person types one tag, looks at which tags come up in the sidebar and how many posts each has,
swaps or adds one, and searches again until the results fit. The script prints that sidebar as
"related tags".

1. **Start**: `booru.py tag <name>` gives the spellings; take the one of the right type with the
   most posts. When not looking for one character, start from the one or two tags that matter
   most.
2. **Search**: `booru.py search <tags> --sheet` prints the total, the related tags, the first 12
   posts (number, id, image address, source) and a numbered thumbnail sheet.
3. **Read the results**:
   - At 0 or a handful of posts, fix the tags first. A tag that does not exist, or has very few
     posts on the whole site, is marked `!` with similar spellings.
   - Related tags read "tag share (posts on the whole site)". The share is over these results
     (at most the first 100); share times the total is about how many posts remain if you add
     that tag.
   - Look at the sheet once to see all 12.
4. **Not right yet: take the next step from the related tags.** Off topic: replace the last tag.
   Too mixed: add one (`solo`, `2girls`, `-comic`, or `-` a character who keeps appearing). Too
   few: drop one. Try one or two candidates per round and keep the best set. Two or three rounds
   are usually enough; do not search in a tight loop, since one search makes four or five
   requests to the site.

## Finding where a picture came from

When reverse image search finds nothing: name the character first, narrow down with the most
distinctive things in the picture as tags, and compare thumbnails by eye. Once the same picture
is found:

- The post page is `https://safebooru.org/index.php?page=post&s=view&id=<id>`.
- `source:` under each post is the original. A pixiv image address
  `i.pximg.net/.../<work id>_p0.png` belongs to the work page
  `https://www.pixiv.net/artworks/<work id>`. Without a source, the artist tag (under `artist` in
  the related tags) leads further.
- One picture is often reposted many times; compare details (signature, watermark, crop), not
  only the character.

## Options

- Rating: `general` (all ages) by default; `--rating safe` and `--rating questionable` allow a
  little more, and then the script always excludes posts tagged as children. `--rating any` sets
  no rating.
- Order: `--sort score` by default (scores here are low; single digits are normal), `--sort new`
  newest, `--sort random` a different set.
- More: `--show 24` shows more posts, `--page 1` the posts 101 to 200.
