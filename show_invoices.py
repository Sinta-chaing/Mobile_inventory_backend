import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.models import Invoice, Purchase

print("--- INVOICES ---")
invoices = Invoice.objects.all().order_by('-createdAt')
print(f"Total invoices: {invoices.count()}")
for inv in invoices:
    print(f"Invoice ID {inv.invoiceId}: Number {inv.invoiceNumber} | Customer: {inv.customerName} | Status: {inv.status} | Total: {inv.grandTotal} | Created: {inv.createdAt}")
    for item in inv.purchases.all():
        print(f"  - Item: {item.product.productName if item.product else 'Unknown'} | Qty: {item.quantity} | Price: {item.pricePerUnit} | Subtotal: {item.subtotal}")
