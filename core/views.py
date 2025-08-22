from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.forms import modelformset_factory
from .models import Event, Heat, EventPart, LaneAssignment, Athlete, EventDivisionSpec, Division, Score, Announcement, Sponsor, Venue
from .utils import aggregate_points_for_division
from django.urls import reverse
from urllib.parse import urlencode

def landing(request):
    now = timezone.localtime()

    # All ongoing heats (any division) whose end_time > now
    ongoing = (Heat.objects
               .filter(start_time__lte=now)
               .select_related('event','division')
               .order_by('-start_time'))
    ongoing = [h for h in ongoing if h.end_time() > now]

    live_group = []
    upcoming_group = []

    if ongoing:
        latest_start = ongoing[0].start_time
        live_group = [h for h in ongoing if h.start_time == latest_start]

    future = list(Heat.objects
                  .filter(start_time__gt=now)
                  .select_related('event','division')
                  .order_by('start_time')[:12])
    if future:
        next_start = future[0].start_time
        upcoming_group = [h for h in future if h.start_time == next_start]

    announcements = Announcement.objects.all()[:5]
    sponsors = Sponsor.objects.all()

    return render(request, 'public/landing.html', {
        'live_group': live_group,
        'upcoming_group': upcoming_group,
        'announcements': announcements,
        'sponsors': sponsors
    })
def horario(request):
    event_num = int(request.GET.get('event', 1))
    event = get_object_or_404(Event, number=event_num)
    heats = Heat.objects.filter(event=event).select_related('division').order_by('division__sort_order','start_time')
    return render(request, 'public/horario.html', {'event': event, 'heats': heats})

POINTS_TABLE = [100,96,92,88,84,80,76,72,68,64,60,56,52,48,44,40,36,32,28,24,20,16,12,8,4]

def _points_for_place(place: int) -> int:
    idx = max(0, place - 1)
    return POINTS_TABLE[idx] if idx < len(POINTS_TABLE) else max(0, 100 - 4*idx)

def _rank_part(part, division):
    """
    Return rows ONLY for athletes who have a meaningful score on this part:
      - time_then_reps: finished+time OR reps present
      - reps: reps present
      - weight: weight present
    Output rows: (athlete, place, points, display_value)
    """
    athletes = list(Athlete.objects.filter(division=division, is_active=True))
    scores = {
        s.athlete_id: s
        for s in Score.objects.filter(part=part, athlete__in=athletes, status='approved')
                              .select_related('athlete')
    }

    def has_valid(s):
        if not s:
            return False
        if part.scoring == 'time_then_reps':
            return (s.finished and s.time_seconds is not None) or (s.reps is not None)
        if part.scoring == 'reps':
            return s.reps is not None
        # weight
        return s.weight is not None

    # keep only athletes with a valid score
    scored = [(a, scores.get(a.id)) for a in athletes if has_valid(scores.get(a.id))]
    if not scored:
        return []  # nothing to rank yet

    def key(pair):
        a, s = pair
        if part.scoring == 'time_then_reps':
            if s.finished and s.time_seconds is not None:
                total = (s.time_seconds or 0) + (s.penalty_seconds or 0)
                return (0, total, 0)         # smaller time is better
            reps = (s.reps or 0) - (s.penalty_reps or 0)
            return (1, -reps, 0)            # more reps is better (bucket behind finishers)
        if part.scoring == 'reps':
            reps = (s.reps or 0) - (s.penalty_reps or 0)
            return (0, -reps, 0)
        # weight
        w = s.weight or 0.0
        return (0, -w, 0)                    # heavier is better

    ordered = sorted(scored, key=key)

    rows = []
    place = 0
    last_key = None
    tie_count = 0
    for a, s in ordered:
        k = key((a, s))
        if last_key is None or k != last_key:
            place = place + 1 + tie_count
            tie_count = 0
            last_key = k
        else:
            tie_count += 1

        pts = _points_for_place(place) if part.counts_as_event else 0

        # pretty display for the score cell
        if part.scoring == 'time_then_reps':
            if s.finished and s.time_seconds is not None:
                total = (s.time_seconds or 0) + (s.penalty_seconds or 0)
                m = int(total // 60); sec = int(round(total - m*60))
                disp = f"{m}:{sec:02d}"
            else:
                disp = f"{(s.reps or 0) - (s.penalty_reps or 0)} reps"
        elif part.scoring == 'reps':
            disp = f"{(s.reps or 0) - (s.penalty_reps or 0)} reps"
        else:
            disp = f"{(s.weight or 0):g}"

        rows.append((a, place, pts, disp))
    return rows

def leaderboard(request):
    sexo = request.GET.get('sexo', 'F')
    cat = request.GET.get('cat', 'sx')
    scope = request.GET.get('scope', 'overall')      # 'overall' | 'part'
    event_num = request.GET.get('event')
    part_slug = request.GET.get('part', '')

    division = get_object_or_404(Division, sex=sexo, category=cat)
    all_parts = list(EventPart.objects.select_related('event').order_by('event__number', 'order'))

    # Per-part view (E1 / E2A / E2B / E3)
    if scope == 'part' and event_num:
        event = get_object_or_404(Event, number=int(event_num))
        parts_for_event = [p for p in all_parts if p.event_id == event.id]
        part = next((p for p in parts_for_event if p.slug == part_slug), None) or (parts_for_event[0] if parts_for_event else None)
        rows_part = _rank_part(part, division) if part else []
        return render(request, 'public/leaderboard.html', {
            'division': division,
            'scope': 'part',
            'all_parts': all_parts,
            'event': event,
            'part': part,
            'rows_part': rows_part,
            'rows': [],
            'parts': all_parts,
        })

    # Overall = sum of points across counting parts, but only athletes with >=1 scored part
    counting_parts = [p for p in all_parts if p.counts_as_event]

    # accumulate per-athlete points only from ranked rows
    athletes = list(Athlete.objects.filter(division=division, is_active=True))
    per_part = {a.id: {} for a in athletes}
    for p in counting_parts:
        for a, place, pts, _disp in _rank_part(p, division):
            per_part[a.id][p.id] = {'place': place, 'points': pts}

    rows = []
    for a in athletes:
        d = per_part.get(a.id, {})
        total = sum(info['points'] for info in d.values())
        if total > 0:               # <-- hide athletes with no results yet
            rows.append((a, total, d))
    rows.sort(key=lambda t: -t[1])

    return render(request, 'public/leaderboard.html', {
        'division': division,
        'scope': 'overall',
        'all_parts': all_parts,
        'rows': rows,
        'parts': counting_parts,
        'event': None,
        'part': None,
    })

def event_list(request):
    # Any old link to /eventos/ (list) goes to the new unified page
    return redirect('eventos')

def event_detail(request, number):
    # Redirect /eventos/<number> → /eventos?event=<number>&cat=sx&sexo=F
    base = reverse('eventos')
    q = urlencode({'event': number, 'cat': 'sx', 'sexo': 'F'})
    return redirect(f'{base}?{q}')

def eventos(request):
    event_num = int(request.GET.get('event', 1))
    sex = request.GET.get('sexo', 'F')                 # 'F' | 'M'
    cat = request.GET.get('cat', 'sx')                 # 'sx' | 'intermedio' | 'rx'
    part_slug = request.GET.get('part', '')            # "", "A", "B", ...

    events = list(Event.objects.order_by('number'))
    event = get_object_or_404(Event, number=event_num)
    division = get_object_or_404(Division, sex=sex, category=cat)

    parts = list(EventPart.objects.filter(event=event).order_by('order'))
    part = next((p for p in parts if p.slug == part_slug), None) or (parts[0] if parts else None)

    spec = None
    cap_seconds = event.cap_seconds
    tiebreak_label = ''
    if part:
        spec = EventDivisionSpec.objects.filter(part=part, division=division).first()
        if spec and spec.cap_seconds:
            cap_seconds = spec.cap_seconds
        if spec and spec.tiebreak_label:
            tiebreak_label = spec.tiebreak_label

    media_urls = []
    if event.media_urls:
        media_urls = [u.strip() for u in event.media_urls.splitlines() if u.strip()]

    spec_gallery = []
    if spec and spec.gallery_urls:
        spec_gallery = [u.strip() for u in spec.gallery_urls.splitlines() if u.strip()]

    return render(request, 'public/eventos.html', {
        'events': events,
        'event': event,
        'division': division,
        'parts': parts,
        'part': part,
        'spec': spec,
        'cap_seconds': cap_seconds,
        'tiebreak_label': tiebreak_label,
        'media_urls': media_urls,
        'spec_gallery': spec_gallery,
    })

EXCLUDE_ROSTER_BIBS = {'SXM10','INTF03','INTM03'}
def athletes(request):
    sex = request.GET.get('sexo','F'); cat = request.GET.get('cat','sx')
    div = get_object_or_404(Division, sex=sex, category=cat)
    roster = Athlete.objects.filter(division=div, is_active=True).exclude(bib__in=EXCLUDE_ROSTER_BIBS).order_by('last_name')
    return render(request, 'public/athletes.html', {'division': div, 'roster': roster})

def sponsors(request):
    return render(request, 'public/sponsors.html', {'sponsors': Sponsor.objects.all()})

def venue_info(request):
    v = Venue.objects.first()
    return render(request, 'public/venue.html', {'venue': v})

@staff_member_required
def staff_scores(request):
    event_num = int(request.GET.get('event', 1))
    sexo = request.GET.get('sexo', 'F')
    cat = request.GET.get('cat', 'sx')
    heat_no = request.GET.get('heat')
    part_slug = request.GET.get('part', '')  # "", "A", "B"...

    div = get_object_or_404(Division, sex=sexo, category=cat)
    event = get_object_or_404(Event, number=event_num)
    parts = list(EventPart.objects.filter(event=event).order_by('order'))
    if not parts:
        return render(request, 'staff/scores.html', {'error': 'Este evento no tiene partes configuradas en /admin.'})

    # Default to first part if none specified
    part = next((p for p in parts if p.slug == part_slug), None) or parts[0]

    heats_qs = Heat.objects.filter(event=event, division=div).order_by('number')
    if not heats_qs.exists():
        return render(request, 'staff/scores.html', {
            'event': event, 'division': div, 'parts': parts, 'part': part,
            'heats_available': [], 'formset': None, 'lanes': [],
            'error': 'No hay heats para esta combinación. Crea heats en /admin.'
        })

    heat = get_object_or_404(Heat, event=event, division=div, number=int(heat_no)) if heat_no else heats_qs.first()
    lanes = LaneAssignment.objects.filter(heat=heat).select_related('athlete').order_by('lane')

    # ensure rows exist for this PART+athlete
    for la in lanes:
        Score.objects.get_or_create(part=part, athlete=la.athlete)

    # different fields per scoring type
    fields = ('notes',)
    if part.scoring == 'time_then_reps':
        fields = ('finished','time_seconds','reps','tiebreak_seconds','penalty_seconds','penalty_reps','notes')
    elif part.scoring == 'reps':
        fields = ('reps','penalty_reps','notes')
    elif part.scoring == 'weight':
        fields = ('weight','notes')

    ScoreFormSet = modelformset_factory(Score, fields=fields, extra=0, can_delete=False)
    qs = Score.objects.filter(part=part, athlete__in=[la.athlete for la in lanes]).select_related('athlete').order_by('athlete__last_name')

    if request.method == 'POST':
        formset = ScoreFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            return redirect(request.get_full_path())
    else:
        formset = ScoreFormSet(queryset=qs)

    return render(request, 'staff/scores.html', {
        'event': event, 'division': div, 'parts': parts, 'part': part,
        'heat': heat, 'lanes': lanes, 'formset': formset,
        'heats_available': list(heats_qs.values_list('number', flat=True))
    })

@staff_member_required
def staff_schedule(request):
    event_num = int(request.GET.get('event', 1))
    event = get_object_or_404(Event, number=event_num)
    HeatFormSet = modelformset_factory(Heat, fields=('start_time',), extra=0)
    qs = Heat.objects.filter(event=event).select_related('division').order_by('division__sort_order','number')

    if request.method == 'POST':
        formset = HeatFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            return redirect(request.get_full_path())
    else:
        formset = HeatFormSet(queryset=qs)

    return render(request, 'staff/schedule.html', {'event': event, 'formset': formset, 'heats': qs})

@login_required
def my_day(request):
    athlete = Athlete.objects.filter(user=request.user, is_active=True).select_related('division').first()

    upcoming = None
    my_lanes = []
    my_scores = []

    if athlete:
        my_lanes = list(
            LaneAssignment.objects
            .filter(athlete=athlete)
            .select_related('heat', 'heat__event', 'heat__division')
            .order_by('heat__start_time')
        )
        now = timezone.localtime()
        for la in my_lanes:
            if la.heat.start_time >= now:
                upcoming = {'heat': la.heat, 'lane': la.lane}
                break

        my_scores = list(
            Score.objects.filter(athlete=athlete)
            .select_related('part', 'part__event')
            .order_by('part__event__number', 'part__order')
        )

    return render(request, 'athlete/my_day.html', {
        'athlete': athlete,
        'upcoming': upcoming,
        'my_lanes': my_lanes,
        'my_scores': my_scores,
    })