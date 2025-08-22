from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Division, Athlete, Event, Heat, LaneAssignment, Sponsor, Venue, Announcement
from datetime import timedelta

class Command(BaseCommand):
    help = "Seed minimal data for testing"

    def handle(self, *args, **kwargs):
        combos = [('M','sx','Sx Masculino'),
                  ('F','sx','Sx Femenino'),
                  ('M','intermedio','Intermedio Masculino'),
                  ('F','intermedio','Intermedio Femenino'),
                  ('M','rx','Rx Masculino'),
                  ('F','rx','Rx Femenino')]
        divs = {}
        for i,(sex,cat,name) in enumerate(combos):
            d,_ = Division.objects.get_or_create(sex=sex, category=cat, defaults={'display_name':name,'sort_order':i})
            divs[(sex,cat)] = d

        e1,_ = Event.objects.get_or_create(number=1, defaults={'name':'Evento 1','type':'time','cap_seconds':600})
        e2,_ = Event.objects.get_or_create(number=2, defaults={'name':'Evento 2','type':'amrap','cap_seconds':600})
        e3,_ = Event.objects.get_or_create(number=3, defaults={'name':'Evento 3','type':'max','cap_seconds':600})

        now = timezone.localtime().replace(minute=0, second=0, microsecond=0)
        for ev in [e1,e2,e3]:
            start = now + timedelta(hours=ev.number-1)
            for idx,div in enumerate(divs.values()):
                for h in [1,2]:
                    Heat.objects.get_or_create(event=ev, division=div, number=h, defaults={
                        'start_time': start + timedelta(minutes=idx*30 + (h-1)*15),
                        'lane_count': 6
                    })

        for div in divs.values():
            prefix = f"{div.category.upper()}{div.sex}"
            for i in range(1,7):
                Athlete.objects.get_or_create(
                    bib=f"{prefix}{i}",
                    division=div,
                    defaults={'first_name':f'Nombre{i}','last_name':f'Apellido{i}','box_gym':'Box Demo'}
                )

        for div in divs.values():
            aths = list(Athlete.objects.filter(division=div)[:6])
            heat = Heat.objects.get(event=e1, division=div, number=1)
            for lane,ath in enumerate(aths, start=1):
                LaneAssignment.objects.get_or_create(heat=heat, lane=lane, athlete=ath)

        Venue.objects.get_or_create(name="Gimnasio Demo", address="San Salvador",
                                    map_link="https://maps.google.com/?q=San+Salvador",
                                    parking_notes="Estacionamiento a un costado",
                                    checkin_notes="Check-in en la entrada principal")
        Sponsor.objects.get_or_create(name="Buffalo", tier="gold")
        Announcement.objects.get_or_create(title="Bienvenidos", body="Competencia inicia pronto", is_pinned=True)

        self.stdout.write(self.style.SUCCESS("Seed complete."))
