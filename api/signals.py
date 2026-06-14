from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Count, Q
from .models import (
    Purchase, Inventory, Invoice, ActivityLog,
    Product, Category, SubCategory, Source, NewStock, Customer, User, ProductAssociation
)
import logging

logger = logging.getLogger(__name__)

# Store previous states for activity logging
_model_previous_states = {}
_invoice_previous_status = {}

# @receiver(post_save, sender=Invoice)
# def calculate_product_associations(sender, instance, created, **kwargs):
#     """
#     Calculate product associations when an invoice is created/updated.
#     This tracks which products are frequently bought together and calculates association percentage.
#     """
#     if instance.status in ['Paid', 'Pending']:  # Only track completed or pending invoices
#         purchases = instance.purchases.filter(product__isnull=False).select_related('product')
#         # Get unique products to avoid counting the same pair multiple times if same product appears multiple times
#         products = list(set(p.product for p in purchases))
#         
#         if len(products) < 2:  # Need at least 2 products to create associations
#             return
#         
#         # Create associations for each pair of products
#         for i, product1 in enumerate(products):
#             for product2 in products[i+1:]:  # Avoid duplicates and self-associations
#                 # Create or update the association in both directions
#                 for prod_a, prod_b in [(product1, product2), (product2, product1)]:
#                     association, _ = ProductAssociation.objects.get_or_create(
#                         product1=prod_a,
#                         product2=prod_b,
#                         defaults={'frequency': 1, 'totalProduct1Purchases': 0}
#                     )
#                     
#                     if not _:  # If association already exists, increment frequency
#                         association.frequency += 1
#                         association.save()
#         
#         # Recalculate association percentages for all affected products
#         all_products_in_invoice = set(products)
#         for product in all_products_in_invoice:
#             update_association_percentages(product)
# 
# 
# def update_association_percentages(product):
#     """
#     Recalculate association percentages for a given product.
#     Association percentage = (times product A and B bought together) / (total times product A purchased)
#     Capped at 100% maximum to prevent invalid percentages.
#     """
#     # Count total purchases for this product
#     total_purchases = Purchase.objects.filter(product=product, invoice__status__in=['Paid', 'Pending']).count()
#     
#     if total_purchases == 0:
#         return
#     
#     # Update all associations for this product
#     associations = ProductAssociation.objects.filter(product1=product)
#     for association in associations:
#         association.totalProduct1Purchases = total_purchases
#         # Cap the percentage at 100% to prevent exceeding 100%
#         percentage = min((association.frequency / total_purchases) * 100, 100.0)
#         association.associationPercentage = percentage
#         association.save(update_fields=['totalProduct1Purchases', 'associationPercentage'])

@receiver(post_save, sender=Purchase)
def update_inventory_on_purchase(sender, instance, created, **kwargs):
    """
    Automatically reduce inventory when a purchase is created.
    This signal is triggered when creating invoices with line items.
    NOTE: Stock validation is done in InvoiceSerializer.create() before creating Purchase records.
    """
    if created:
        try: 
            inventory = Inventory.objects.get(product=instance.product)
            
            # Reduce inventory (validation already done in serializer)
            inventory.quantity -= instance.quantity
            inventory.save()
        except Inventory.DoesNotExist:
            # This should not happen if serializer validation works correctly
            # But we log it for debugging purposes
            print(f"WARNING: No inventory record found for product: {instance.product.productName}")
            pass  # Don't raise error in signal to avoid transaction issues


# ==================== ACTIVITY LOGGING ====================

def get_current_user_from_instance(instance):
    """Helper function to extract user from various model instances."""
    user_fields = ['createdByUser', 'addedByUser', 'recordedByUser']
    for field in user_fields:
        if hasattr(instance, field):
            user = getattr(instance, field)
            if user:
                return user
    return None


# ----- Product Activity Logging -----
@receiver(post_save, sender=Product)
def log_product_activity(sender, instance, created, **kwargs):
    """Log when products are created or updated."""
    user = get_current_user_from_instance(instance)
    
    if created:
        ActivityLog.objects.create(
            user=user,
            actionType='CREATE_PRODUCT',
            description=f"Created product: {instance.productName} (SKU: {instance.skuCode})"
        )
    else:
        ActivityLog.objects.create(
            user=user,
            actionType='UPDATE_PRODUCT',
            description=f"Updated product: {instance.productName} (SKU: {instance.skuCode})"
        )


@receiver(post_delete, sender=Product)
def log_product_deletion(sender, instance, **kwargs):
    """Log when products are deleted."""
    ActivityLog.objects.create(
        user=None,
        actionType='DELETE_PRODUCT',
        description=f"Deleted product: {instance.productName} (SKU: {instance.skuCode})"
    )


# ----- Category Activity Logging -----
@receiver(post_save, sender=Category)
def log_category_activity(sender, instance, created, **kwargs):
    """Log when categories are created or updated."""
    if created:
        ActivityLog.objects.create(
            user=None,
            actionType='CREATE_CATEGORY',
            description=f"Created category: {instance.name}"
        )
    else:
        ActivityLog.objects.create(
            user=None,
            actionType='UPDATE_CATEGORY',
            description=f"Updated category: {instance.name}"
        )


@receiver(post_delete, sender=Category)
def log_category_deletion(sender, instance, **kwargs):
    """Log when categories are deleted."""
    ActivityLog.objects.create(
        user=None,
        actionType='DELETE_CATEGORY',
        description=f"Deleted category: {instance.name}"
    )


# ----- Inventory Activity Logging -----
@receiver(pre_save, sender=Inventory)
def store_previous_inventory_quantity(sender, instance, **kwargs):
    """Store previous inventory quantity for comparison."""
    if instance.pk:
        try:
            previous = Inventory.objects.get(pk=instance.pk)
            _model_previous_states[f'inventory_{instance.pk}'] = previous.quantity
        except Inventory.DoesNotExist:
            pass


@receiver(post_save, sender=Inventory)
def log_inventory_activity(sender, instance, created, **kwargs):
    """Log when inventory is created or updated."""
    if created:
        ActivityLog.objects.create(
            user=None,
            actionType='CREATE_INVENTORY',
            description=f"Created inventory for: {instance.product.productName} - Quantity: {instance.quantity} @ {instance.location}"
        )
    else:
        previous_qty = _model_previous_states.get(f'inventory_{instance.pk}')
        if previous_qty is not None and previous_qty != instance.quantity:
            change = instance.quantity - previous_qty
            change_text = f"+{change}" if change > 0 else str(change)
            ActivityLog.objects.create(
                user=None,
                actionType='UPDATE_INVENTORY',
                description=f"Inventory adjusted for {instance.product.productName}: {previous_qty} → {instance.quantity} ({change_text})"
            )
        # Clean up
        if f'inventory_{instance.pk}' in _model_previous_states:
            del _model_previous_states[f'inventory_{instance.pk}']


# ----- NewStock Activity Logging -----
@receiver(post_save, sender=NewStock)
def log_newstock_activity(sender, instance, created, **kwargs):
    """Log when new stock is added."""
    if created:
        ActivityLog.objects.create(
            user=instance.addedByUser,
            actionType='ADD_STOCK',
            description=f"Added {instance.quantity} units of {instance.inventory.product.productName} from {instance.supplier.name if instance.supplier else 'Unknown supplier'}"
        )


# ----- Invoice Activity Logging -----
@receiver(pre_save, sender=Invoice)
def store_previous_invoice_status_and_set_paid_timestamp(sender, instance, **kwargs):
    """Store previous invoice status and set paidAt timestamp when changing to Paid."""
    if instance.pk:
        try:
            previous = Invoice.objects.get(pk=instance.pk)
            _invoice_previous_status[instance.pk] = previous.status
            
            # If status is changing from non-Paid to Paid, set paidAt timestamp
            if previous.status != 'Paid' and instance.status == 'Paid':
                instance.paidAt = timezone.now()
        except Invoice.DoesNotExist:
            pass


@receiver(post_save, sender=Invoice)
def log_invoice_activity(sender, instance, created, **kwargs):
    """Log when invoices are created or updated."""
    user = instance.createdByUser
    
    if created:
        ActivityLog.objects.create(
            user=user,
            actionType='CREATE_INVOICE',
            description=f"Created invoice #{instance.invoiceId} for {instance.customer.name if instance.customer else 'Unknown'} - Total: ${instance.grandTotal} - Status: {instance.status}"
        )
    else:
        # Check if status changed
        previous_status = _invoice_previous_status.get(instance.pk)
        if previous_status and previous_status != instance.status:
            ActivityLog.objects.create(
                user=user,
                actionType='UPDATE_INVOICE_STATUS',
                description=f"Invoice #{instance.invoiceId} status changed: {previous_status} → {instance.status}"
            )
        else:
            ActivityLog.objects.create(
                user=user,
                actionType='UPDATE_INVOICE',
                description=f"Updated invoice #{instance.invoiceId}"
            )


@receiver(post_delete, sender=Invoice)
def log_invoice_deletion(sender, instance, **kwargs):
    """Log when invoices are deleted."""
    ActivityLog.objects.create(
        user=instance.createdByUser,
        actionType='DELETE_INVOICE',
        description=f"Deleted invoice #{instance.invoiceId}"
    )


# ----- Customer Activity Logging -----
@receiver(post_save, sender=Customer)
def log_customer_activity(sender, instance, created, **kwargs):
    """Log when customers are created or updated."""
    if created:
        ActivityLog.objects.create(
            user=None,
            actionType='CREATE_CUSTOMER',
            description=f"Created customer: {instance.name} ({instance.customerType})"
        )
    else:
        ActivityLog.objects.create(
            user=None,
            actionType='UPDATE_CUSTOMER',
            description=f"Updated customer: {instance.name}"
        )


@receiver(post_delete, sender=Customer)
def log_customer_deletion(sender, instance, **kwargs):
    """Log when customers are deleted."""
    ActivityLog.objects.create(
        user=None,
        actionType='DELETE_CUSTOMER',
        description=f"Deleted customer: {instance.name}"
    )


# ----- User Activity Logging -----
@receiver(post_save, sender=User)
def log_user_activity(sender, instance, created, **kwargs):
    """Log when users are created or updated."""
    if created:
        ActivityLog.objects.create(
            user=None,
            actionType='CREATE_USER',
            description=f"Created user: {instance.username} with role: {instance.role}"
        )
    else:
        ActivityLog.objects.create(
            user=instance,
            actionType='UPDATE_USER',
            description=f"Updated user profile: {instance.username}"
        )


@receiver(post_delete, sender=User)
def log_user_deletion(sender, instance, **kwargs):
    """Log when users are deleted."""
    ActivityLog.objects.create(
        user=None,
        actionType='DELETE_USER',
        description=f"Deleted user: {instance.username}"
    )


@receiver(pre_save, sender=Product)
def store_original_product_image(sender, instance, **kwargs):
    """Store the original image path to detect if it changes."""
    if instance.pk:
        try:
            orig = Product.objects.get(pk=instance.pk)
            instance._original_image = orig.image
        except Product.DoesNotExist:
            instance._original_image = None
    else:
        instance._original_image = None


@receiver(post_save, sender=Product)
def auto_index_product_image(sender, instance, created, **kwargs):
    """
    Automatically index product images to Qdrant vector database when:
    1. A new product is created with an image
    2. An existing product's image is updated
    
    This allows the product to be searchable via image similarity search.
    """
    try:
        # Only process if product has an image
        if not instance.image or instance.image.strip() == '':
            logger.info(f"Skipping indexing for Product(id={instance.productId}): No image")
            return
        
        # Only process if created or if the image has changed
        original_image = getattr(instance, '_original_image', None)
        if not created and original_image == instance.image:
            logger.info(f"Skipping indexing for Product(id={instance.productId}): Image did not change")
            return
        
        from .image_search_service import index_product_image
        
        # Index the product image
        logger.info(f"Auto-indexing product image: {instance.productName} (Product ID: {instance.productId})")
        index_product_image(
            product_id=instance.productId,
            image_url=instance.image,
            product_name=instance.productName,
            sku_code=instance.skuCode
        )
        logger.info(f"✓ Successfully indexed: {instance.productName}")
        
    except Exception as e:
        # Log the error but don't crash the product save operation
        logger.error(f"✗ Failed to index product image for {instance.productName} (ID: {instance.productId}): {str(e)}")
        # In production, you might want to send an alert or retry with Celery
        # For now, we silently continue to avoid blocking product creation