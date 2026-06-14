import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.models import Invoice

for inv in Invoice.objects.filter(status='Paid'):
    print(f"Invoice {inv.invoiceId} ({inv.invoiceNumber}): Status={inv.status}, paidAt={inv.paidAt}, createdAt={inv.createdAt}")
