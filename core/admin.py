from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import (
    Division, Athlete, Event, Heat, LaneAssignment,
    Announcement, Sponsor, Venue,
    EventPart, EventDivisionSpec, Score
)

@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ('display_name','sex','category','sort_order')
    list_editable = ('sort_order',)
    list_filter = ('sex','category')
    search_fields = ('display_name',)

@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    list_display = ('bib','first_name','last_name','division','box_gym','is_active')
    list_filter = ('division','is_active')
    search_fields = ('bib','first_name','last_name','box_gym')

class LaneInline(admin.TabularInline):
    model = LaneAssignment
    extra = 0

@admin.register(Heat)
class HeatAdmin(admin.ModelAdmin):
    list_display = ('event','division','number','start_time','lane_count')
    list_filter = ('event','division')
    inlines = [LaneInline]

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('number','name','type','cap_seconds','tiebreak_enabled')
    list_editable = ('name','type','cap_seconds','tiebreak_enabled')
    search_fields = ('name',)

@admin.register(EventPart)
class EventPartAdmin(admin.ModelAdmin):
    list_display = ('event','slug','name','scoring','counts_as_event','order')
    list_filter = ('event','scoring','counts_as_event')
    list_editable = ('scoring','counts_as_event','order')
    search_fields = ('name','slug')

@admin.register(EventDivisionSpec)
class EventDivisionSpecAdmin(admin.ModelAdmin):
    list_display = ('part','division','cap_seconds','tiebreak_label','has_poster')
    list_filter = ('part__event__number','division__category','division__sex')
    search_fields = ('division__display_name','part__name')
    readonly_fields = ('poster_preview',)
    fieldsets = (
        ('Clave', {'fields': ('part','division')}),
        ('Visual', {'fields': ('poster','poster_preview','gallery_urls')}),
        ('Texto (opcional)', {'fields': ('description_md','cap_seconds','tiebreak_label')}),
    )
    def has_poster(self, obj): return bool(obj.poster)
    has_poster.boolean = True
    def poster_preview(self, obj):
        if obj.poster:
            return mark_safe(f'<img src="{obj.poster.url}" style="max-width:100%;border:1px solid #e5e7eb;border-radius:.5rem;" />')
        return "—"

@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    # IMPORTANT: use fields that exist on the new Score model
    list_display = ('part','athlete','finished','time_seconds','reps','weight','tiebreak_seconds','status','created_at')
    list_filter = ('part','status','athlete__division')
    search_fields = ('athlete__first_name','athlete__last_name','athlete__bib')

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title','is_pinned','created_at')
    list_editable = ('is_pinned',)
    search_fields = ('title',)

@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = ('name','tier','link_url')
    list_filter = ('tier',)
    search_fields = ('name',)

@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ('name','address','map_link')
    search_fields = ('name','address')
