import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.models import Inventory
from api.serializers import InventorySerializer
from rest_framework.test import APIRequestFactory

factory = APIRequestFactory()
request = factory.get('/api/inventory/')

# Create a test user who is administrator to see all fields
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    user = User.objects.get(username='testuser')
except User.DoesNotExist:
    user = User.objects.create_user(username='testuser', password='testpass', role='administrator')

request.user = user

inventory_items = Inventory.objects.select_related('product', 'product__subcategory__category', 'product__source').all()
serializer = InventorySerializer(inventory_items, many=True, context={'request': request})

# Print formatted Python dictionary reps
for item in list(serializer.data[:2]):
    print("ITEM:")
    for k, v in item.items():
        print(f"  {k}: {v} ({type(v).__name__})")
