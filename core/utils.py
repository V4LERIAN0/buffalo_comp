from typing import List, Dict, Tuple
from .models import Score, EventPart, Division, Athlete

def standard_competition_points(place: int) -> int:
    # 1st=100, 2nd=96, 3rd=92, ... subtract 4 per place, not below 0
    pts = 100 - (place - 1) * 4
    return max(0, pts)

def rank_part_for_division(part: EventPart, division: Division) -> List[Tuple[int, dict]]:
    """
    Returns list of (athlete_id, metrics dict, place) sorted by rank for this part within a division.
    metrics dict includes the values used for ranking (for display/debug).
    """
    # all athletes in this division with a score for this part
    qs = (Score.objects
          .filter(part=part, athlete__division=division)
          .select_related('athlete'))

    def sort_key(s: Score):
        if part.scoring == 'time_then_reps':
            # Finished first, sort by (time+penalty) ASC; else by (reps - penalty) DESC; tiebreak_seconds ASC
            finished = 1 if s.finished else 0
            t = (s.time_seconds or 1e12) + (s.penalty_seconds or 0.0)
            r = (s.reps or 0) - (s.penalty_reps or 0)
            tb = s.tiebreak_seconds or 1e12
            # Finished should come before non-finished → sort by (-finished, time, -reps, tiebreak)
            return (-finished, t, -r, tb)

        elif part.scoring == 'reps':
            r = (s.reps or 0) - (s.penalty_reps or 0)
            return (-r, s.athlete.last_name, s.athlete.first_name)

        elif part.scoring == 'weight':
            w = (s.weight or 0.0)
            return (-w, s.athlete.last_name, s.athlete.first_name)

        return (0,)

    scores = sorted(qs, key=sort_key)

    # Assign places with standard competition ranking (1,1,3,…).
    places = []
    prev_key = None
    place = 0
    i = 0
    while i < len(scores):
        s = scores[i]
        k = sort_key(s)
        if prev_key is None or k != prev_key:
            # new place starts here = previous place + number tied previously
            place = len(places) + 1
        prev_key = k

        metrics = {
            'finished': s.finished,
            'time': s.time_seconds,
            'reps': s.reps,
            'weight': s.weight,
            'tiebreak': s.tiebreak_seconds,
            'pen_sec': s.penalty_seconds,
            'pen_reps': s.penalty_reps,
        }
        places.append((s.athlete_id, metrics, place))
        i += 1

    return places

def aggregate_points_for_division(parts: List[EventPart], division: Division) -> Dict[int, dict]:
    """
    Returns a mapping: athlete_id → {'points': total_points, 'by_part': {part.id: {'place':p,'points':pts}}}
    Only counts parts where counts_as_event=True.
    """
    table: Dict[int, dict] = {}
    for part in parts:
        rows = rank_part_for_division(part, division)
        # compute points with standard competition ranking (ties share place & points)
        # need to know how many tied for a given place: we can recompute by grouping by place
        from collections import defaultdict
        by_place = defaultdict(list)
        for aid, metrics, place in rows:
            by_place[place].append((aid, metrics))

        # award points
        for place in sorted(by_place.keys()):
            pts = standard_competition_points(place)
            for aid, metrics in by_place[place]:
                entry = table.setdefault(aid, {'points': 0, 'by_part': {}})
                if part.counts_as_event:
                    entry['points'] += pts
                entry['by_part'][part.id] = {'place': place, 'points': pts, 'metrics': metrics}
    return table
