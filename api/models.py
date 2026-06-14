from django.db import models

from django.contrib.auth.models import AbstractUser

# Reusable role choices for model
ROLE_CHOICES = [
    ('administrator', 'Administrator'),
    ('manager', 'Manager'),
    ('staff', 'Staff'),
]

# custom user model with extra fields (role)
class User(AbstractUser):
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='administrator')

    def __str__(self):
        return f"{self.username} ({self.role})"

class UserProfile(models.Model):
    profileId = models.AutoField(primary_key=True)
    user = models.OneToOneField('User', on_delete=models.CASCADE, related_name='profile')
    qrCodeImage = models.ImageField(upload_to='qr_codes/', null=True, blank=True)  # QR code image file
    businessName = models.CharField(max_length=255, null=True, blank=True)
    businessAddress = models.TextField(null=True, blank=True)
    businessPhone = models.CharField(max_length=50, null=True, blank=True)
    businessEmail = models.EmailField(max_length=255, null=True, blank=True)
    taxId = models.CharField(max_length=100, null=True, blank=True)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


class Category(models.Model):
    categoryId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
class SubCategory(models.Model):
    subcategoryId = models.AutoField(primary_key=True)
    category = models.ForeignKey('Category', on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=255)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} → {self.category.name}"
    
class Source(models.Model):
    sourceId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)  # Supplier or origin name
    sourceUrl = models.URLField(max_length=500, null=True, blank=True)  # Website or contact link
    contactPerson = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    district = models.CharField(max_length=255, null=True, blank=True)  # District/Province
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    
# Reusable status choices for product availability
STATUS_CHOICES = [
    ('Active', 'Active'),
    ('Inactive', 'Inactive'),
    ('Discount', 'Discount'),
]

class Product(models.Model):
    productId = models.AutoField(primary_key=True)
    productName = models.CharField(max_length=255)
    description = models.TextField()
    image = models.CharField(max_length=500, null=True, blank=True)  # URL or path to image
    skuCode = models.CharField(max_length=100, unique=True)
    unit = models.CharField(max_length=50)  # e.g., pcs, box, kg
    costPrice = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Original price from supplier
    salePrice = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Sale price to customers
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Discount percentage
    subcategory = models.ForeignKey('SubCategory', on_delete=models.CASCADE, related_name='products')
    source = models.ForeignKey('Source', on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.productName} ({self.skuCode})"

    def save(self, *args, **kwargs):
        """Auto-set status to Discount if discount > 0"""
        if self.discount and self.discount > 0:
            self.status = 'Discount'
        super().save(*args, **kwargs)


class Inventory(models.Model):
    inventoryId = models.AutoField(primary_key=True)
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='inventory_records')
    quantity = models.IntegerField()
    reorderLevel = models.IntegerField()
    location = models.CharField(max_length=255)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.productName} @ {self.location} — {self.quantity} units"


class NewStock(models.Model):
    newstockId = models.AutoField(primary_key=True)
    inventory = models.ForeignKey('Inventory', on_delete=models.CASCADE, related_name='stock_entries')
    quantity = models.IntegerField()
    purchasePrice = models.DecimalField(max_digits=10, decimal_places=2)
    receivedDate = models.DateField()
    supplier = models.ForeignKey('Source', on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_supplied')
    addedByUser = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_added')
    note = models.TextField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Stock +{self.quantity} → {self.inventory.product.productName} on {self.receivedDate}"
    
# Reusable customer type choices
CUSTOMER_TYPE_CHOICES = [
    ('Individual', 'Individual'),
    ('Business', 'Business'),
]

class Customer(models.Model):
    customerId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    businessAddress = models.TextField()
    phone = models.CharField(max_length=50)
    email = models.EmailField(blank=True, null=True)
    customerType = models.CharField(max_length=20, choices=CUSTOMER_TYPE_CHOICES)
    firstPurchaseDate = models.DateField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.customerType})"


# Reusable enums for payment method and invoice status
PAYMENT_METHOD_CHOICES = [
    ('Cash', 'Cash'),
    ('KHQR', 'KHQR'),
]

INVOICE_STATUS_CHOICES = [
    ('Pending', 'Pending'),
    ('Paid', 'Paid'),
    ('Cancelled', 'Cancelled'),
]

class Invoice(models.Model):
    invoiceId = models.AutoField(primary_key=True)
    invoiceNumber = models.CharField(max_length=20, unique=True, null=True, blank=True)  # Format: YYYY-NNN
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    customerName = models.CharField(max_length=255, default='Guest')  # Direct customer name input
    customerPhone = models.CharField(max_length=50, null=True, blank=True)  # Optional phone
    createdByUser = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='invoices_created')
    totalBeforeDiscount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    grandTotal = models.DecimalField(max_digits=10, decimal_places=2)
    paymentMethod = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    note = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=INVOICE_STATUS_CHOICES, default='Pending')
    paidAt = models.DateTimeField(null=True, blank=True)  # Timestamp when invoice was marked as paid
    
    # KHQR Payment Fields
    khqrCodeString = models.TextField(null=True, blank=True)  # QR code string generated by KHQR SDK
    khqrMd5 = models.CharField(max_length=255, null=True, blank=True)  # MD5 hash of QR code
    khqrTransactionHash = models.CharField(max_length=255, null=True, blank=True)  # Full transaction hash (64 chars)
    khqrShortHash = models.CharField(max_length=8, null=True, blank=True)  # Short transaction hash (8 chars)
    khqrDeeplink = models.TextField(null=True, blank=True)  # Payment deeplink URL
    khqrLastCheckedAt = models.DateTimeField(null=True, blank=True)  # Last time we checked payment status
    khqrPaymentData = models.JSONField(null=True, blank=True)  # Store full payment response from KHQR
    
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        invoice_num = self.invoiceNumber or f"#{self.invoiceId}"
        return f"Invoice {invoice_num} — {self.customerName} — {self.status}"

    def save(self, *args, **kwargs):
        """Generate invoice number if not already set"""
        if not self.invoiceNumber:
            from datetime import datetime
            current_year = datetime.now().year
            
            # Find the highest sequence number in the database for the current year
            year_prefix = f"INV-{current_year}-"
            invoice_numbers = Invoice.objects.filter(
                invoiceNumber__startswith=year_prefix
            ).values_list('invoiceNumber', flat=True)
            
            max_seq = 0
            for num in invoice_numbers:
                try:
                    parts = num.split('-')
                    if len(parts) == 3:
                        seq = int(parts[2])
                        if seq > max_seq:
                            max_seq = seq
                except (ValueError, IndexError):
                    continue
            
            sequence_number = max_seq + 1
            self.invoiceNumber = f"INV-{current_year}-{sequence_number:03d}"
        
        super().save(*args, **kwargs)


class Purchase(models.Model):
    purchaseId = models.AutoField(primary_key=True)
    invoice = models.ForeignKey('Invoice', on_delete=models.CASCADE, related_name='purchases')
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases')
    quantity = models.IntegerField()
    pricePerUnit = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quantity} × {self.product.productName if self.product else 'Unknown'} → Invoice #{self.invoice.invoiceId}"
    

class ProductAssociation(models.Model):
    associationId = models.AutoField(primary_key=True)
    product1 = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='associations_from')
    product2 = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='associations_to')
    frequency = models.IntegerField(default=1)  # Number of times bought together
    associationPercentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Percentage of co-purchases relative to product1's total purchases
    totalProduct1Purchases = models.IntegerField(default=0)  # Total times product1 was purchased (for percentage calculation)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product1', 'product2')  # Ensure only one association per pair

    def __str__(self):
        return f"{self.product1.productName} → {self.product2.productName} ({self.associationPercentage}%)"
    
# Reusable enums for payment method and transaction status
TRANSACTION_METHOD_CHOICES = [
    ('Cash', 'Cash'),
    ('Card', 'Card'),
    ('KHQR', 'KHQR'),
    ('BankTransfer', 'BankTransfer'),
    ('Other', 'Other'),
]

TRANSACTION_STATUS_CHOICES = [
    ('Pending', 'Pending'),
    ('Completed', 'Completed'),
    ('Failed', 'Failed'),
    ('Refunded', 'Refunded'),
]

class Transaction(models.Model):
    transactionId = models.AutoField(primary_key=True)
    invoice = models.ForeignKey('Invoice', on_delete=models.CASCADE, related_name='transactions')
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, related_name='transactions')
    amountPaid = models.DecimalField(max_digits=10, decimal_places=2)
    paymentMethod = models.CharField(max_length=20, choices=TRANSACTION_METHOD_CHOICES)
    transactionStatus = models.CharField(max_length=20, choices=TRANSACTION_STATUS_CHOICES)
    paymentReference = models.CharField(max_length=255, null=True, blank=True)
    transactionDate = models.DateTimeField()
    recordedByUser = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='transactions_recorded')

    def __str__(self):
        return f"Txn #{self.transactionId} — {self.transactionStatus} ({self.amountPaid})"
    
class ActivityLog(models.Model):
    logId = models.AutoField(primary_key=True)
    user = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='activity_logs')
    actionType = models.CharField(max_length=100)  # e.g., 'ADD_PRODUCT', 'DELETE_INVOICE'
    description = models.TextField()
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.actionType} by {self.user.username if self.user else 'Unknown'}"