from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
import builtins

register = template.Library()

@register.filter
def zip_lists(a, b):
    return builtins.zip(a, b)

@register.filter
def get_item(d, key):
    try:
        return d.get(key)
    except Exception:
        return None

@register.filter
def markdownify(text):
    if not text:
        return ""
    try:
        import markdown
        html = markdown.markdown(text, extensions=["extra", "sane_lists"])
        return mark_safe(html)
    except Exception:
        return mark_safe(escape(text).replace("\n", "<br>"))
    
@register.filter
def get_item(d, key):
    try:
        return d.get(key)
    except Exception:
        return None

@register.filter
def score_display(s):
    """Pretty print a Score according to its part.scoring."""
    if not s or not getattr(s, 'part', None):
        return ''
    p = s.part
    if p.scoring == 'time_then_reps':
        if s.finished and s.time_seconds is not None:
            total = (s.time_seconds or 0) + (s.penalty_seconds or 0)
            m = int(total // 60); sec = int(round(total - m*60))
            return f"{m}:{sec:02d}"
        reps = (s.reps or 0) - (s.penalty_reps or 0)
        return f"{reps} reps"
    if p.scoring == 'reps':
        return f"{(s.reps or 0) - (s.penalty_reps or 0)} reps"
    # weight
    return f"{(s.weight or 0):g}"
