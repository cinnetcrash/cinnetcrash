# How this profile is built

`README.md` and everything in `assets/` are **generated**. Don't hand-edit them —
the next scheduled run will overwrite your changes. Edit `config.json` instead.

```
build_profile.py    the generator
config.json         what to say and which repos to feature
assets/*.svg        generated graphics, committed so GitHub can serve them
README.md           generated profile page
```

## Running it

```bash
GITHUB_TOKEN=$(gh auth token) python3 build_profile.py

# see the output without writing anything
GITHUB_TOKEN=$(gh auth token) python3 build_profile.py --dry-run
```

Only the standard library is needed. GitHub Actions re-runs it every Monday and
on any change to the script or config (`.github/workflows/refresh-profile.yml`),
and commits the result only when something actually changed.

## Editing `config.json`

| Key | What it controls |
|---|---|
| `intro` / `outro` | Markdown above and below the generated blocks |
| `sections` | Ordered groups of featured repos, rendered as tables |
| `blurbs` | Per-repo one-liner. Falls back to the repo's GitHub description |
| `sites` | The "Live sites" table |

A repo named in `sections` that no longer exists is skipped silently, so renaming
or deleting one won't break the build. Featured repos are also what the timeline
chart draws.

## The graphics

Three cards, each rendered twice (light and dark) and switched with a `<picture>`
element so GitHub picks the right one for the viewer's theme.

| Card | Shows |
|---|---|
| `stats` | Public repos, stars, distinct languages, years on GitHub |
| `languages` | Share of repositories by primary language |
| `timeline` | First commit → last push for each featured project |

They are plain SVG written by the script — no badge services, no tracking pixels,
no external requests when someone views the profile. Nothing breaks if a
third-party service goes down or starts rate-limiting.

### About the colours

The categorical slots are **not** GitHub's language colours. Those fail a
colour-vision check: Shell `#89e051` and JavaScript `#f1e05a` sit ΔE 13 apart for
normal vision and ΔE 3.3 under protanopia — effectively the same colour for many
readers. The palette in `THEMES` is validated in both modes (worst adjacent pair
ΔE 9.1 protan / 19.6 normal in light; 8.4 / 19.3 in dark), segments are separated
by a 2 px surface gap, and every segment carries a direct text label, so identity
never depends on colour alone.

Colour is bound to the language name via `LANG_SLOT_ORDER`, not to its rank —
a language moving up or down the list does not repaint the others. Languages
beyond the first eight are folded into an explicit "Other" segment rather than
being dropped.

### About the timeline

An earlier version of this card was a "pushes per month" column chart. It counted
each repository once, at its most recent push, so a single day of bulk edits
across many repos produced a spike that looked like a year of work. Span of
activity — created to last push — is something the API actually knows, so that is
what it draws now.
