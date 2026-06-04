import os
import sys
import django

# Add backend directory to sys.path
sys.path.append(r'e:\DSE-Y3-S2\Mobile\Inventory_management\Mobile_inventory_backend')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.models import Product

# We target the test products shown in your inventory screen (ID 25 to 31)
test_ids = [25, 26, 27, 28, 29, 30, 31]
products_to_delete = Product.objects.filter(productId__in=test_ids)

if not products_to_delete.exists():
    print("No test products found to delete.")
    sys.exit(0)

print(f"Found {products_to_delete.count()} test product(s) to delete:")
for p in products_to_delete:
    print(f"  - ID {p.productId}: {p.productName}")

# Perform cascading delete
deleted_count, details = products_to_delete.delete()
print(f"Successfully deleted {deleted_count} database record(s) total.")
print("Delete details:", details)
