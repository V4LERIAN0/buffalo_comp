import csv
from pathlib import Path
from typing import Optional
from django.core.files.base import ContentFile
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings

from core.models import (
    Division, Athlete, Event, Heat, LaneAssignment,
    Sponsor, Venue, EventPart, EventDivisionSpec
)

def _bool(v):
    if v is None: return False
    s = str(v).strip().lower()
    return s in ('1','true','t','yes','y','si','sí')

def _int(v, default=None):
    if v in (None, ''): return default
    try: return int(v)
    except: return default

def _float(v, default=None):
    if v in (None, ''): return default
    try: return float(v)
    except: return default

def _str(v):
    return '' if v is None else str(v).strip()

def _localize(dt_str: str):
    # expects 'YYYY-MM-DD HH:MM'
    if not dt_str: return None
    from datetime import datetime
    naive = datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M")
    # treat as local time (settings.TIME_ZONE)
    tz = timezone.get_default_timezone()
    return timezone.make_aware(naive, tz)

def _copy_file_to_media(src_path: str, subdir: str) -> Optional[str]:
    """Copy a local file into MEDIA_ROOT/subdir and return the relative path."""
    if not src_path:
        return None
    p = Path(src_path)
    if not p.exists():
        print(f"  [warn] file not found: {src_path}")
        return None
    target_dir = Path(settings.MEDIA_ROOT) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / p.name
    if p.resolve() != target.resolve():
        target.write_bytes(p.read_bytes())
    rel = f"{subdir}/{p.name}"
    return rel

class Command(BaseCommand):
    help = "Import competition data from a folder of CSV files."

    def add_arguments(self, parser):
        parser.add_argument('--path', required=True, help='Path to folder containing CSVs')

    def handle(self, *args, **opts):
        folder = Path(opts['path'])
        if not folder.exists():
            raise CommandError(f"Folder does not exist: {folder}")

        self.stdout.write(self.style.MIGRATE_HEADING(f"Importing from {folder}"))

        # 1) Divisions
        divs_by_key = {}
        path = folder / 'divisions.csv'
        if path.exists():
            with path.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    sex = _str(row.get('sex')).upper()  # M/F
                    category = _str(row.get('category')).lower()  # sx/intermedio/rx
                    display_name = _str(row.get('display_name'))
                    sort_order = _int(row.get('sort_order'), 0)
                    d, _ = Division.objects.get_or_create(
                        sex=sex, category=category,
                        defaults={'display_name': display_name or f"{category} {sex}", 'sort_order': sort_order}
                    )
                    if display_name and d.display_name != display_name:
                        d.display_name = display_name
                        d.sort_order = sort_order
                        d.save()
                    divs_by_key[(sex, category)] = d
            self.stdout.write(self.style.SUCCESS(f"Divisions: {len(divs_by_key)}"))

        # 2) Events
        events_by_num = {}
        path = folder / 'events.csv'
        if path.exists():
            with path.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    number = _int(row.get('number'))
                    name = _str(row.get('name'))
                    typ = _str(row.get('type')).lower()  # time/amrap/max (legacy)
                    cap_seconds = _int(row.get('cap_seconds'), 0)
                    tiebreak_enabled = _bool(row.get('tiebreak_enabled'))
                    description_md = row.get('description_md') or ''
                    if number is None:
                        continue
                    e, created = Event.objects.get_or_create(number=number, defaults={
                        'name': name or f"Evento {number}",
                        'type': typ or 'time',
                        'cap_seconds': cap_seconds or 0,
                        'tiebreak_enabled': tiebreak_enabled,
                        'description_md': description_md
                    })
                    # update if changed
                    changed = False
                    if name and e.name != name: e.name, changed = name, True
                    if typ and e.type != typ: e.type, changed = typ, True
                    if cap_seconds is not None and e.cap_seconds != cap_seconds: e.cap_seconds, changed = cap_seconds, True
                    if e.tiebreak_enabled != tiebreak_enabled: e.tiebreak_enabled, changed = tiebreak_enabled, True
                    if description_md and e.description_md != description_md: e.description_md, changed = description_md, True
                    if changed: e.save()
                    events_by_num[number] = e
            self.stdout.write(self.style.SUCCESS(f"Events: {len(events_by_num)}"))

        # 3) Event Parts
        parts = {}
        path = folder / 'event_parts.csv'
        if path.exists():
            with path.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    ev_no = _int(row.get('event_number'))
                    slug = _str(row.get('slug'))
                    name = _str(row.get('name'))
                    scoring = _str(row.get('scoring'))  # time_then_reps / reps / weight
                    counts = _bool(row.get('counts_as_event'))
                    order = _int(row.get('order'), 1)
                    e = events_by_num.get(ev_no)
                    if not e:
                        self.stdout.write(self.style.WARNING(f"  Skip part: event {ev_no} not found"))
                        continue
                    p, _ = EventPart.objects.get_or_create(event=e, slug=slug, defaults={
                        'name': name or (f"Part {slug}" if slug else 'Main'),
                        'scoring': scoring or 'time_then_reps',
                        'counts_as_event': counts,
                        'order': order,
                    })
                    # updates
                    changed = False
                    if name and p.name != name: p.name, changed = name, True
                    if scoring and p.scoring != scoring: p.scoring, changed = scoring, True
                    if p.counts_as_event != counts: p.counts_as_event, changed = counts, True
                    if p.order != order: p.order, changed = order, True
                    if changed: p.save()
                    parts[(ev_no, slug)] = p
            self.stdout.write(self.style.SUCCESS(f"Event parts: {len(parts)}"))

        # 4) Event Division Specs
        path = folder / 'event_division_specs.csv'
        if path.exists():
            with path.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    ev_no = _int(row.get('event_number'))
                    slug = _str(row.get('part_slug'))
                    sex = _str(row.get('sex')).upper()
                    category = _str(row.get('category')).lower()
                    cap_seconds = _int(row.get('cap_seconds'), None)
                    tiebreak_label = _str(row.get('tiebreak_label'))
                    description_md = row.get('description_md') or ''
                    p = parts.get((ev_no, slug))
                    d = divs_by_key.get((sex, category))
                    if not p or not d:
                        self.stdout.write(self.style.WARNING(f"  Skip spec: part ({ev_no},{slug}) or division ({sex},{category}) missing"))
                        continue
                    spec, _ = EventDivisionSpec.objects.get_or_create(part=p, division=d, defaults={
                        'cap_seconds': cap_seconds,
                        'tiebreak_label': tiebreak_label,
                        'description_md': description_md,
                    })
                    changed = False
                    if cap_seconds is not None and spec.cap_seconds != cap_seconds: spec.cap_seconds, changed = cap_seconds, True
                    if tiebreak_label and spec.tiebreak_label != tiebreak_label: spec.tiebreak_label, changed = tiebreak_label, True
                    if description_md and spec.description_md != description_md: spec.description_md, changed = description_md, True
                    if changed: spec.save()
            self.stdout.write(self.style.SUCCESS("Event division specs imported"))

        # 5) Athletes
        athletes_by_bib = {}
        path = folder / 'athletes.csv'
        if path.exists():
            with path.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    bib = _str(row.get('bib'))
                    if not bib:
                        continue
                    first = _str(row.get('first_name'))
                    last = _str(row.get('last_name'))
                    disp = _str(row.get('display_name'))
                    box = _str(row.get('box_gym'))
                    sex = _str(row.get('sex')).upper()
                    category = _str(row.get('category')).lower()
                    photo_path = _str(row.get('photo_path'))
                    div = divs_by_key.get((sex, category))
                    if not div:
                        self.stdout.write(self.style.WARNING(f"  Skip athlete {bib}: division ({sex},{category}) not found"))
                        continue
                    a, created = Athlete.objects.get_or_create(bib=bib, defaults={
                        'first_name': first, 'last_name': last, 'display_name': disp,
                        'box_gym': box, 'division': div
                    })
                    changed = False
                    if a.first_name != first: a.first_name, changed = first, True
                    if a.last_name != last: a.last_name, changed = last, True
                    if disp and a.display_name != disp: a.display_name, changed = disp, True
                    if box and a.box_gym != box: a.box_gym, changed = box, True
                    if a.division_id != div.id: a.division, changed = div, True
                    # photo
                    if photo_path:
                        rel = _copy_file_to_media(photo_path, 'athletes')
                        if rel and (not a.photo or a.photo.name != rel):
                            a.photo.name = rel
                            changed = True
                    if changed: a.save()
                    athletes_by_bib[bib] = a
            self.stdout.write(self.style.SUCCESS(f"Athletes: {len(athletes_by_bib)}"))

        # 6) Heats
        heats_index = {}
        path = folder / 'heats.csv'
        if path.exists():
            with path.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    ev_no = _int(row.get('event_number'))
                    sex = _str(row.get('sex')).upper()
                    category = _str(row.get('category')).lower()
                    number = _int(row.get('number'))
                    start_time = _localize(_str(row.get('start_time')))
                    e = events_by_num.get(ev_no)
                    d = divs_by_key.get((sex, category))
                    if not e or not d or not number:
                        self.stdout.write(self.style.WARNING(f"  Skip heat: missing event/division/number"))
                        continue
                    h, _ = Heat.objects.get_or_create(event=e, division=d, number=number, defaults={
                        'start_time': start_time or timezone.now(), 'lane_count': 8
                    })
                    if start_time and h.start_time != start_time:
                        h.start_time = start_time
                        h.save()
                    heats_index[(ev_no, sex, category, number)] = h
            self.stdout.write(self.style.SUCCESS(f"Heats imported: {len(heats_index)}"))

        # 7) Lane assignments
        path = folder / 'lanes.csv'
        if path.exists():
            with path.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    ev_no = _int(row.get('event_number'))
                    sex = _str(row.get('sex')).upper()
                    category = _str(row.get('category')).lower()
                    heat_no = _int(row.get('heat_number'))
                    lane = _int(row.get('lane'))
                    bib = _str(row.get('bib'))
                    h = heats_index.get((ev_no, sex, category, heat_no))
                    a = athletes_by_bib.get(bib)
                    if not h or not a or not lane:
                        self.stdout.write(self.style.WARNING(f"  Skip lane: missing heat/athlete/lane for bib={bib}"))
                        continue
                    la, _ = LaneAssignment.objects.get_or_create(heat=h, lane=lane, defaults={'athlete': a})
                    if la.athlete_id != a.id:
                        la.athlete = a
                        la.save()
            self.stdout.write(self.style.SUCCESS("Lane assignments imported"))

        # 8) Sponsors
        path = folder / 'sponsors.csv'
        if path.exists():
            with path.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    name = _str(row.get('name'))
                    if not name: continue
                    tier = _str(row.get('tier'))
                    link = _str(row.get('link_url'))
                    logo_path = _str(row.get('logo_path'))
                    s, _ = Sponsor.objects.get_or_create(name=name, defaults={'tier': tier, 'link_url': link})
                    changed = False
                    if tier and s.tier != tier: s.tier, changed = tier, True
                    if link and s.link_url != link: s.link_url, changed = link, True
                    if logo_path:
                        rel = _copy_file_to_media(logo_path, 'sponsors')
                        if rel and (not s.logo or s.logo.name != rel):
                            s.logo.name = rel
                            changed = True
                    if changed: s.save()
            self.stdout.write(self.style.SUCCESS("Sponsors imported"))

        # 9) Venue (single row)
        path = folder / 'venue.csv'
        if path.exists():
            with path.open(newline='', encoding='utf-8') as f:
                rows = list(csv.DictReader(f))
                if rows:
                    r = rows[0]
                    name = _str(r.get('name')) or 'Sede'
                    v, _ = Venue.objects.get_or_create(name=name)
                    v.address = _str(r.get('address'))
                    v.map_link = _str(r.get('map_link'))
                    v.parking_notes = r.get('parking_notes') or ''
                    v.checkin_notes = r.get('checkin_notes') or ''
                    # Optional socials if you added those fields
                    if hasattr(v, 'instagram_url'): v.instagram_url = _str(r.get('instagram_url'))
                    if hasattr(v, 'facebook_url'): v.facebook_url = _str(r.get('facebook_url'))
                    v.save()
            self.stdout.write(self.style.SUCCESS("Venue imported"))

        self.stdout.write(self.style.MIGRATE_HEADING("Import complete ✅"))
