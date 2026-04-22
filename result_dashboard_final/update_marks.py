import os
import django
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'result_dashboard.settings')
django.setup()

from results.models import StudentResult

# Get Kaushal Kumar
results = StudentResult.objects.filter(name__icontains="Kaushal Kumar")
for res in results:
    res.marks = random.randint(50, 60)
    res.save()
    print(f"Updated {res.subject} marks for {res.name} to {res.marks}")

print("Update complete!")
