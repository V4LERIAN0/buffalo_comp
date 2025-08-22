from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta

class EventPart(models.Model):
    SCORING_CHOICES = (
        ('time_then_reps', 'Time (if finished) else Reps'),
        ('reps', 'Reps'),
        ('weight', 'Weight'),
    )
    event = models.ForeignKey('Event', on_delete=models.CASCADE, related_name='parts')
    name = models.CharField(max_length=80)               # e.g., "Part A", "Part B" or just "Main"
    slug = models.CharField(max_length=2, blank=True)    # "", "A", "B"...
    scoring = models.CharField(max_length=20, choices=SCORING_CHOICES)
    counts_as_event = models.BooleanField(default=True)  # Event 2 has A & B → both True
    order = models.PositiveSmallIntegerField(default=1)  # display / ranking order

    class Meta:
        ordering = ['event__number', 'order']

    def __str__(self):
        disp = f"E{self.event.number}"
        if self.slug:
            disp += f"{self.slug}"
        return f"{disp} – {self.name}"

class EventDivisionSpec(models.Model):
    """
    Per-division/sex variations: cap overrides, tiebreak label, and rich description.
    """
    part = models.ForeignKey(EventPart, on_delete=models.CASCADE, related_name='division_specs')
    division = models.ForeignKey('Division', on_delete=models.CASCADE)
    cap_seconds = models.PositiveIntegerField(null=True, blank=True)  # override if needed
    tiebreak_label = models.CharField(max_length=120, blank=True)     # e.g., "30 air squats finished time"
    description_md = models.TextField(blank=True)                     # full standards for this division/sex
    poster = models.ImageField(upload_to='events/', blank=True)  # main poster for this división/part
    gallery_urls = models.TextField(blank=True, help_text="Una URL por línea (opcional)")

    class Meta:
        unique_together = ('part', 'division')

    def __str__(self):
        return f"{self.part} · {self.division.display_name}"
    
class Division(models.Model):
    SEX_CHOICES = (('M','Masculino'), ('F','Femenino'))
    CAT_CHOICES = (('sx','Sx'), ('intermedio','Intermedio'), ('rx','Rx'))
    sex = models.CharField(max_length=1, choices=SEX_CHOICES)
    category = models.CharField(max_length=12, choices=CAT_CHOICES)
    display_name = models.CharField(max_length=40)
    sort_order = models.PositiveIntegerField(default=0)
    class Meta:
        unique_together = ('sex','category')
        ordering = ['sort_order']
    def __str__(self): return self.display_name

class Athlete(models.Model):
    bib = models.CharField(max_length=10, unique=True)
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    display_name = models.CharField(max_length=120, blank=True)
    box_gym = models.CharField(max_length=120, blank=True)
    division = models.ForeignKey(Division, on_delete=models.PROTECT)
    photo = models.ImageField(upload_to='athletes/', blank=True)
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL)  # optional login
    is_active = models.BooleanField(default=True)
    def name(self): return self.display_name or f"{self.first_name} {self.last_name}"
    def __str__(self): return f"{self.bib} - {self.name()}"

class Event(models.Model):
    TYPE_CHOICES = (('time','Time'), ('amrap','AMRAP'), ('max','Max'))
    number = models.PositiveSmallIntegerField()   # 1..3
    name = models.CharField(max_length=80)
    type = models.CharField(max_length=8, choices=TYPE_CHOICES)
    cap_seconds = models.PositiveIntegerField(default=0)
    tiebreak_enabled = models.BooleanField(default=False)
    description_md = models.TextField(blank=True)   # WOD + estándares (Markdown)
    media_urls = models.TextField(blank=True)       # optional: 1 per line
    class Meta: ordering = ['number']
    def __str__(self): return f"E{self.number} - {self.name}"

class Heat(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    division = models.ForeignKey(Division, on_delete=models.PROTECT)
    number = models.PositiveSmallIntegerField()     # Heat 1, 2…
    start_time = models.DateTimeField()
    lane_count = models.PositiveSmallIntegerField(default=8)
    class Meta:
        unique_together = ('event','division','number')
        ordering = ['start_time']
    def __str__(self): return f"{self.event} {self.division} H{self.number}"
    def end_time(self):
        return self.start_time + timedelta(seconds=self.event.cap_seconds or 0)

class LaneAssignment(models.Model):
    heat = models.ForeignKey(Heat, on_delete=models.CASCADE, related_name='lanes')
    lane = models.PositiveSmallIntegerField()
    athlete = models.ForeignKey(Athlete, on_delete=models.PROTECT)
    class Meta:
        unique_together = ('heat','lane')
        ordering = ['lane']

class Score(models.Model):
    STATUS = (('pending','Pending'), ('approved','Approved'))

    part = models.ForeignKey(EventPart, on_delete=models.CASCADE, null=True, blank=True)
    athlete = models.ForeignKey('Athlete', on_delete=models.CASCADE)

    # Store all possible primitives; ranking uses only what the part.scoring needs.
    time_seconds = models.FloatField(null=True, blank=True)    # for "time_then_reps"
    reps = models.IntegerField(null=True, blank=True)          # for "reps" or fallback for time cap
    weight = models.FloatField(null=True, blank=True)          # for "weight"
    finished = models.BooleanField(default=False)               # for time-based events
    tiebreak_seconds = models.FloatField(null=True, blank=True)

    penalty_seconds = models.FloatField(default=0)
    penalty_reps = models.IntegerField(default=0)

    notes = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default='approved')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('part', 'athlete')

    def __str__(self):
        return f"{self.athlete} · {self.part}"
class Announcement(models.Model):
    title = models.CharField(max_length=120)
    body = models.TextField()
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-is_pinned','-created_at']

class Sponsor(models.Model):
    name = models.CharField(max_length=120)
    tier = models.CharField(max_length=20, blank=True)  # gold/silver/bronze
    logo = models.ImageField(upload_to='sponsors/', blank=True)
    link_url = models.URLField(blank=True)

class Venue(models.Model):
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=200)
    map_link = models.URLField(blank=True)
    parking_notes = models.TextField(blank=True)
    checkin_notes = models.TextField(blank=True)