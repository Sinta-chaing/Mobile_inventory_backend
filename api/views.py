from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action, api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.db import transaction
from django.core.files.storage import default_storage
from django.conf import settings
from django.utils import timezone
import logging
import traceback
from .khqr_service import KHQRService

logger = logging.getLogger(__name__)
from .permissions import (
    IsAdmin,
    IsManager,
    IsStaff,
    IsAdminOrManager,
    IsManagerOrReadOnly
)
from .models import (
    User,
    UserProfile,
    Product, 
    Inventory, 
    Category, 
    SubCategory, 
    Source,
    NewStock,
    Customer,
    Invoice,
    Purchase,
    Transaction,
    ActivityLog,
    ProductAssociation
)
from .serializers import (
    UserSerializer,
    UserProfileSerializer,
    ProductSerializer, 
    InventorySerializer, 
    CategorySerializer, 
    SubCategorySerializer, 
    SourceSerializer,
    NewStockSerializer,
    CustomerSerializer,
    InvoiceSerializer,
    PurchaseNestedSerializer,
    TransactionSerializer,
    ActivityLogSerializer,
    ProductAssociationSerializer,
    RelatedProductSerializer
)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_image(request):
    """Upload product image with validation"""
    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response({'error': 'No file provided'}, status=400)
    
    import uuid
    from pathlib import Path
    
    # Validate file type
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    file_name = file_obj.name.lower() if hasattr(file_obj, 'name') else None
    
    if not file_name:
        return Response({'error': 'Invalid file - no name provided'}, status=400)
    
    # Extract extension, handle multiple dots safely
    file_extension = Path(file_name).suffix.lower()
    
    if not file_extension or file_extension not in allowed_extensions:
        sorted_extensions = ', '.join(sorted(allowed_extensions))
        return Response({
            'error': f'Invalid file type. Allowed types: {sorted_extensions}'
        }, status=400)
    
    # Validate file size (max 5MB)
    max_size = 5 * 1024 * 1024  # 5MB in bytes
    if file_obj.size > max_size:
        return Response({
            'error': 'File too large. Maximum size is 5MB'
        }, status=400)
    
    try:
        # Generate unique filename to prevent conflicts
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Save the file with unique name
        file_name = default_storage.save(f'products/{unique_filename}', file_obj)
        file_url = default_storage.url(file_name)
        
        # Return the full URL
        full_url = request.build_absolute_uri(file_url)
        return Response({'url': full_url}, status=201)
    except Exception as e:
        return Response({'error': f'Failed to upload image: {str(e)}'}, status=500)

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdmin] # Only administrators should manage users

class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Users can only see their own profile
        if self.request.user.role == 'administrator':
            return UserProfile.objects.all()
        return UserProfile.objects.filter(user=self.request.user)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly] # Admins/Managers can manage, Staff can view
    
class SubCategoryViewSet(viewsets.ModelViewSet):
    queryset = SubCategory.objects.all()
    serializer_class = SubCategorySerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly] # Admins/Managers can manage, Staff can view

class SourceViewSet(viewsets.ModelViewSet):
    queryset = Source.objects.all()
    serializer_class = SourceSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly] # Admins/Managers can manage, Staff can view

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly] # Managers/Admins can create/edit, Staff can view

class InventoryViewSet(viewsets.ModelViewSet):
    queryset = Inventory.objects.select_related('product', 'product__source').all()
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly] # Managers/Admins can adjust, Staff can view

class NewStockViewSet(viewsets.ModelViewSet):
    queryset = NewStock.objects.all()
    serializer_class = NewStockSerializer
    permission_classes = [IsAuthenticated] # Any authenticated user can track stock additions
    
    @transaction.atomic 
    def perform_create(self, serializer):
        """Add new stock and update inventory atomically"""
        new_stock_quantity = serializer.validated_data.get('quantity')
        inventory_item = serializer.validated_data.get('inventory')
        
        # Validate quantity is positive
        if new_stock_quantity is None or new_stock_quantity <= 0:
            raise ValidationError({"quantity": "Stock quantity must be a positive number"})
        
        # Update inventory quantity
        inventory_item.quantity += new_stock_quantity
        inventory_item.save(update_fields=['quantity', 'updatedAt'])
        
        # Save the new stock record with current user
        serializer.save(addedByUser=self.request.user)

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly] # Managers/Admins can manage customers, Staff can view
    
    def create(self, request, *args, **kwargs):
        """Override create to add detailed error logging"""
        print(f"[Customer Create] Received data: {request.data}")
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print(f"[Customer Create] Validation errors: {serializer.errors}")
        return super().create(request, *args, **kwargs)

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly] # Managers/Admins can create/manage invoices, Staff can view
    
    def perform_create(self, serializer):
        """Automatically set the createdByUser to the current user"""
        invoice = serializer.save(createdByUser=self.request.user)
        
        # Auto-generate KHQR QR code if payment method is KHQR
        if invoice.paymentMethod == 'KHQR' and invoice.status == 'Pending':
            try:
                khqr_service = KHQRService()
                qr_data = khqr_service.generate_qr_code(
                    invoice_id=invoice.invoiceId,
                    amount=invoice.grandTotal,
                    currency='USD'  # You can make this dynamic based on your needs
                )
                
                if qr_data:
                    invoice.khqrCodeString = qr_data['qr_string']
                    invoice.khqrMd5 = qr_data['md5_hash']
                    
                    # Generate deeplink
                    deeplink = khqr_service.generate_deeplink(qr_data['qr_string'])
                    if deeplink:
                        invoice.khqrDeeplink = deeplink
                    
                    invoice.save()
            except Exception as e:
                # Log error but don't fail invoice creation
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to generate KHQR for invoice #{invoice.invoiceId}: {str(e)}")
    
    def perform_update(self, serializer):
        """Update invoice - transaction creation handled by signals"""
        serializer.save()
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def generate_khqr(self, request, pk=None):
        """
        Generate KHQR QR code for an existing invoice
        POST /api/invoices/{id}/generate_khqr/
        """
        invoice = self.get_object()
        
        if invoice.status != 'Pending':
            return Response(
                {'error': 'QR code can only be generated for pending invoices'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If QR code already exists, return it instead of regenerating
        if invoice.khqrCodeString and invoice.khqrMd5:
            logger.info(f"Using existing QR code for invoice #{invoice.invoiceId}")
            return Response({
                'success': True,
                'qr_string': invoice.khqrCodeString,
                'md5_hash': invoice.khqrMd5,
                'deeplink': invoice.khqrDeeplink or '',
                'amount': float(invoice.grandTotal),
                'invoice_id': invoice.invoiceId
            })
        
        try:
            khqr_service = KHQRService()
            
            # Validate configuration
            if not khqr_service.bakong_account_id:
                logger.error("KHQR_BAKONG_ACCOUNT_ID is not configured")
                return Response(
                    {'error': 'KHQR payment is not configured. Please set KHQR_BAKONG_ACCOUNT_ID in settings.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            logger.info(f"Generating NEW KHQR for invoice #{invoice.invoiceId}, amount: {invoice.grandTotal}")
            
            # Convert USD to KHR if needed (1 USD ≈ 4000 KHR)
            # Bakong typically uses KHR currency
            amount_khr = float(invoice.grandTotal) * 4000
            
            qr_data = khqr_service.generate_qr_code(
                invoice_id=invoice.invoiceId,
                amount=amount_khr,
                currency='KHR'
            )
            
            if not qr_data:
                logger.error(f"Failed to generate QR code for invoice #{invoice.invoiceId}")
                return Response(
                    {'error': 'Failed to generate QR code. Please check server logs.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Update invoice with QR data (ONLY ONCE!)
            invoice.khqrCodeString = qr_data['qr_string']
            invoice.khqrMd5 = qr_data['md5_hash']
            invoice.paymentMethod = 'KHQR'
            
            # Generate deeplink (optional, may fail if no access token)
            deeplink = khqr_service.generate_deeplink(qr_data['qr_string'])
            if deeplink:
                invoice.khqrDeeplink = deeplink
            
            invoice.save()
            
            logger.info(f"Successfully generated KHQR for invoice #{invoice.invoiceId}")
            
            return Response({
                'success': True,
                'qr_string': qr_data['qr_string'],
                'md5_hash': qr_data['md5_hash'],
                'deeplink': deeplink,
                'amount': float(invoice.grandTotal),
                'invoice_id': invoice.invoiceId
            })
        except Exception as e:
            logger.error(f"Error generating KHQR for invoice #{invoice.invoiceId}: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                {'error': f'Failed to generate QR code: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def check_payment(self, request, pk=None):
        """
        Check KHQR payment status for an invoice
        POST /api/invoices/{id}/check_payment/
        """
        invoice = self.get_object()
        
        logger.info(f"Checking payment for invoice #{invoice.invoiceId}, MD5: {invoice.khqrMd5}")
        
        if not invoice.khqrMd5:
            return Response(
                {'error': 'No KHQR payment associated with this invoice'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            khqr_service = KHQRService()
            
            # Check if KHQR service is properly configured
            if not khqr_service.get_access_token():
                logger.warning("KHQR API token not available")
                return Response(
                    {
                        'error': 'KHQR payment verification unavailable',
                        'detail': 'KHQR API token is not configured. Please check KHQR_TOKEN in .env file.',
                        'paid': False
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            
            # Check transaction status by MD5
            logger.info(f"Calling KHQR API to check transaction...")
            transaction_data = khqr_service.check_transaction_by_md5(invoice.khqrMd5)
            logger.info(f"KHQR API response: {transaction_data}")
            
            # Update last checked timestamp
            invoice.khqrLastCheckedAt = timezone.now()
            
            if transaction_data:
                # Payment successful!
                invoice.status = 'Paid'
                
                # Use payment timestamp from Bakong (in milliseconds)
                # createdDateMs: Transaction creation timestamp
                # acknowledgedDateMs: Transaction acknowledged timestamp
                payment_timestamp_ms = transaction_data.get('acknowledgedDateMs') or transaction_data.get('createdDateMs')
                
                if payment_timestamp_ms:
                    try:
                        # Convert milliseconds to seconds for datetime
                        from datetime import datetime
                        invoice.paidAt = datetime.fromtimestamp(payment_timestamp_ms / 1000)
                    except Exception as e:
                        logger.error(f"Error parsing timestamp {payment_timestamp_ms}: {e}")
                        invoice.paidAt = timezone.now()
                else:
                    invoice.paidAt = timezone.now()
                
                invoice.khqrTransactionHash = transaction_data.get('hash', '')
                invoice.khqrShortHash = transaction_data.get('hash', '')[:8] if transaction_data.get('hash') else ''
                invoice.khqrPaymentData = transaction_data
                invoice.save()
                
                logger.info(f"Payment confirmed for invoice #{invoice.invoiceId} at {invoice.paidAt}")
                logger.info(f"Transaction details: {transaction_data}")
                
                return Response({
                    'success': True,
                    'paid': True,
                    'payment_timestamp': invoice.paidAt.isoformat() if invoice.paidAt else None,
                    'transaction_hash': invoice.khqrTransactionHash,
                    'from_account': transaction_data.get('fromAccountId'),
                    'amount': transaction_data.get('amount'),
                    'currency': transaction_data.get('currency'),
                    'payment_data': transaction_data,
                    'invoice_status': invoice.status
                })
            else:
                # Payment not found yet
                invoice.save()
                return Response({
                    'success': True,
                    'paid': False,
                    'message': 'Payment not found yet',
                    'invoice_status': invoice.status
                })
        except Exception as e:
            logger.error(f"Error checking payment: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response(
                {
                    'error': 'Failed to check payment status',
                    'detail': str(e),
                    'paid': False
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def mark_as_paid(self, request, pk=None):
        """
        Manually mark KHQR invoice as paid
        POST /api/invoices/{id}/mark_as_paid/
        
        Use this when:
        - Automatic payment verification is not available (NBC account not approved)
        - You've verified payment in your Bakong app manually
        """
        invoice = self.get_object()
        
        if invoice.status == 'Paid':
            return Response({
                'success': True,
                'message': 'Invoice is already marked as paid',
                'invoice_status': invoice.status
            })
        
        if invoice.paymentMethod != 'KHQR':
            return Response(
                {'error': 'This endpoint is only for KHQR invoices'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark as paid with current timestamp
        invoice.status = 'Paid'
        invoice.paidAt = timezone.now()
        invoice.save()
        
        logger.info(f"Invoice #{invoice.invoiceId} manually marked as paid by {request.user.username}")
        
        return Response({
            'success': True,
            'paid': True,
            'message': 'Invoice manually marked as paid',
            'invoice_status': invoice.status,
            'paid_at': invoice.paidAt.isoformat()
        })
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def batch_check_payments(self, request):
        """
        Batch check payment status for multiple pending KHQR invoices
        POST /api/invoices/batch_check_payments/
        """
        # Get all pending KHQR invoices with MD5 hashes
        pending_invoices = Invoice.objects.filter(
            status='Pending',
            paymentMethod='KHQR',
            khqrMd5__isnull=False
        ).exclude(khqrMd5='')
        
        if not pending_invoices.exists():
            return Response({
                'success': True,
                'message': 'No pending KHQR invoices to check',
                'checked': 0,
                'paid': 0
            })
        
        try:
            khqr_service = KHQRService()
            md5_list = [inv.khqrMd5 for inv in pending_invoices]
            
            # Batch check transactions
            results = khqr_service.batch_check_transactions_by_md5(md5_list)
            
            if not results:
                return Response(
                    {'error': 'Batch check failed'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Process results
            paid_count = 0
            updated_invoices = []
            
            for result in results:
                md5_hash = result.get('md5')
                result_status = result.get('status')
                transaction_data = result.get('data')
                
                # Find invoice by MD5
                try:
                    invoice = pending_invoices.get(khqrMd5=md5_hash)
                    invoice.khqrLastCheckedAt = timezone.now()
                    
                    if result_status == 'SUCCESS' and transaction_data:
                        # Mark as paid
                        invoice.status = 'Paid'
                        invoice.paidAt = timezone.now()
                        invoice.khqrTransactionHash = transaction_data.get('hash', '')
                        invoice.khqrShortHash = transaction_data.get('hash', '')[:8]
                        invoice.khqrPaymentData = transaction_data
                        paid_count += 1
                        updated_invoices.append(invoice.invoiceId)
                    
                    invoice.save()
                except Invoice.DoesNotExist:
                    continue
            
            return Response({
                'success': True,
                'checked': len(md5_list),
                'paid': paid_count,
                'updated_invoices': updated_invoices
            })
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in batch payment check: {str(e)}")
            return Response(
                {'error': f'Batch check failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PurchaseViewSet(viewsets.ModelViewSet):
    queryset = Purchase.objects.all()
    serializer_class = PurchaseNestedSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly] # Managers/Admins can create/manage purchases, Staff can view

class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly] # Managers/Admins can manage transactions, Staff can view

class ActivityLogViewSet(viewsets.ModelViewSet):
    queryset = ActivityLog.objects.all()
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated, IsAdminOrManager] # Only Managers/Admins should view activity logs


class ProductAssociationViewSet(viewsets.ModelViewSet):
    queryset = ProductAssociation.objects.all().order_by('-associationPercentage', '-frequency')
    serializer_class = ProductAssociationSerializer
    permission_classes = [IsAuthenticated] # All authenticated users can view associations
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def by_product(self, request):
        """
        Get products that are associated with a specific product.
        Query parameter: product_id (required)
        Returns products bought together with the specified product, ordered by association percentage.
        """
        product_id = request.query_params.get('product_id')
        
        if not product_id:
            return Response(
                {'error': 'product_id query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            product = Product.objects.get(productId=product_id)
        except Product.DoesNotExist:
            return Response(
                {'error': f'Product with id {product_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get all associations for this product
        associations = ProductAssociation.objects.filter(
            product1=product
        ).order_by('-associationPercentage', '-frequency')
        
        serializer = RelatedProductSerializer(associations, many=True)
        return Response(serializer.data)