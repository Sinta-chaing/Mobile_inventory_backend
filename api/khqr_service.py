"""
KHQR Payment Service
Handles Bakong KHQR API integration for payment processing
"""
import requests
import hashlib
import logging
import base64
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from django.conf import settings
from bakong_khqr import KHQR

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

logger = logging.getLogger(__name__)


class KHQRService:
    """Service class for handling KHQR payment operations"""
    
    def __init__(self):
        self.base_url = getattr(settings, 'KHQR_BASE_URL', '')
        self.email = getattr(settings, 'KHQR_EMAIL', '')
        self.bakong_token = getattr(settings, 'KHQR_TOKEN', '')
        self.bakong_account_id = getattr(settings, 'KHQR_BAKONG_ACCOUNT_ID', '')
        self.merchant_name = getattr(settings, 'KHQR_MERCHANT_NAME', '')
        self.merchant_city = getattr(settings, 'KHQR_MERCHANT_CITY', '')
        self.app_icon_url = getattr(settings, 'KHQR_APP_ICON_URL', '')
        self.app_name = getattr(settings, 'KHQR_APP_NAME', '')
        self.app_deeplink_callback = getattr(settings, 'KHQR_APP_DEEPLINK_CALLBACK', '')
        self._access_token = None

    def _sanitize_khqr_text(self, value: str, fallback: str = '', max_length: int = 25) -> str:
        """Normalize label text to a conservative KHQR-safe form."""
        cleaned = ''.join(ch for ch in str(value).strip() if ch.isalnum() or ch in ' ._-')
        cleaned = ' '.join(cleaned.split())
        if not cleaned:
            cleaned = fallback
        return cleaned[:max_length]
    
    def get_access_token(self) -> Optional[str]:
        """
        Get or renew access token for KHQR API
        Returns: Access token string or None if failed
        """
        # First, check if token is already cached
        if self._access_token:
            return self._access_token
        
        # Second, use the token from settings/env if available
        if self.bakong_token:
            self._access_token = self.bakong_token
            logger.info("Using KHQR token from configuration")
            return self._access_token
        
        # Third, try to renew token via API (only if email is configured)
        if not self.email:
            logger.debug("No KHQR token or email configured")
            return None
            
        try:
            url = f"{self.base_url}/v1/renew_token"
            payload = {"email": self.email}
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('responseCode') == 0:
                self._access_token = data.get('data', {}).get('token')
                logger.info("KHQR access token renewed successfully")
                return self._access_token
            else:
                logger.debug(f"Token renewal not available: {data.get('responseMessage')}")
                return None
        except Exception as e:
            logger.debug(f"KHQR token not available (API registration may be required): {str(e)}")
            return None
    
    def generate_qr_code(
        self,
        invoice_id: int,
        amount: Decimal,
        currency: str = 'USD',
        store_label: str | None = None,
        phone_number: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate KHQR QR code for an invoice
        
        Args:
            invoice_id: The invoice ID
            amount: Payment amount
            currency: Currency code (USD or KHR)
        
        Returns:
            Dictionary containing qr_string, md5_hash, and other details
        """
        try:
            # Validate required configuration
            if not self.bakong_account_id:
                logger.error("KHQR_BAKONG_ACCOUNT_ID is not configured")
                raise ValueError("KHQR_BAKONG_ACCOUNT_ID is required but not configured")
            
            if not self.merchant_name:
                logger.error("KHQR_MERCHANT_NAME is not configured")
                raise ValueError("KHQR_MERCHANT_NAME is required but not configured")
            
            logger.info(f"Generating KHQR QR code: invoice_id={invoice_id}, amount={amount}, currency={currency}")
            logger.info(f"Using bakong_account_id: {self.bakong_account_id}")
            logger.info(f"Using merchant_name: {self.merchant_name}")
            logger.info(f"Using merchant_city: {self.merchant_city}")

            currency_code = (currency or 'USD').upper()
            if currency_code == 'KHR':
                amount_value = int(Decimal(str(amount)).quantize(Decimal('1')))
            else:
                amount_value = float(Decimal(str(amount)).quantize(Decimal('0.01')))

            merchant_name = self._sanitize_khqr_text(self.merchant_name, fallback='Merchant')
            merchant_city = self._sanitize_khqr_text(self.merchant_city or 'Phnom Penh', fallback='Phnom Penh')
            
            # Initialize KHQR in a way that works across package versions.
            try:
                khqr = KHQR(self.bakong_token) if self.bakong_token else KHQR()
            except TypeError:
                khqr = KHQR()
            
            # Generate simplified KHQR - use amount with merchant info only (no invoice details).
            # Bakong format validation rejects complex invoice structures as [MAPP-KHQR-INV-FORMAT].
            # Try the simplest valid format that Bakong accepts.
            qr_data = khqr.create_qr(
                bank_account=self.bakong_account_id,
                merchant_name=merchant_name,
                merchant_city=merchant_city,
                amount=amount_value,
                currency=currency_code,
                store_label='',
                phone_number='',
                bill_number='',
                terminal_label='',
            )
            qr_string = qr_data if isinstance(qr_data, str) else str(qr_data)
            
            # Calculate MD5 hash locally to avoid package-version differences.
            md5_hash = hashlib.md5(qr_string.encode('utf-8')).hexdigest()

            qr_image = self.generate_qr_image(qr_string)
            
            logger.info(f"Generated KHQR QR code for invoice #{invoice_id}, MD5: {md5_hash}")
            
            # Print to terminal for debugging
            print(f"\n{'='*80}")
            print(f"KHQR QR Code Generated for Invoice #{invoice_id}")
            print(f"{'='*80}")
            print(f"Amount: {amount} {currency}")
            print(f"MD5: {md5_hash}")
            print(f"QR String ({len(qr_string)} chars):")
            print(qr_string)
            print(f"{'='*80}\n")
            
            return {
                'qr_string': qr_string,
                'qr_image': qr_image,
                'md5_hash': md5_hash,
                'amount': float(amount),
                'currency': currency,
                'invoice_id': invoice_id
            }
        except Exception as e:
            logger.error(f"Error generating QR code for invoice #{invoice_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def generate_qr_image(self, qr_string: str) -> Optional[str]:
        """Generate a canonical KHQR image from a QR string using standard library."""
        # Use qrcode library for reliable, scannable image generation
        if QRCODE_AVAILABLE:
            try:
                qr = qrcode.QRCode(
                    version=None,  # Auto-detect version
                    error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
                    box_size=10,
                    border=4,
                )
                qr.add_data(qr_string)
                qr.make(fit=True)
                
                # Generate PIL image
                img = qr.make_image(fill_color="black", back_color="white")
                
                # Convert to base64 data URI
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
                data_uri = f"data:image/png;base64,{img_base64}"
                
                logger.info("Generated QR image using qrcode library")
                return data_uri
            except Exception as e:
                logger.warning(f"qrcode library generation failed: {e}")
                return None
        
        # If qrcode library not available, log and return None
        logger.debug("qrcode library not available, QR image generation skipped")
        return None
    
    def generate_deeplink(self, qr_string: str) -> Optional[str]:
        """
        Generate payment deeplink from QR code string
        
        Args:
            qr_string: The KHQR QR code string
        
        Returns:
            Deeplink URL or None if failed
        """
        token = self.get_access_token()
        if not token:
            logger.debug("Deeplink not available: No API token (NBC registration required)")
            return None
        
        try:
            url = f"{self.base_url}/v1/generate_deeplink_by_qr"
            payload = {
                "qr": qr_string,
                "sourceInfo": {
                    "appIconUrl": self.app_icon_url,
                    "appName": self.app_name,
                    "appDeepLinkCallback": self.app_deeplink_callback
                }
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('responseCode') == 0:
                deeplink = data.get('data', {}).get('shortLink')
                logger.info("Generated KHQR deeplink successfully")
                return deeplink
            else:
                logger.debug(f"Deeplink not available: {data.get('responseMessage')} (requires NBC merchant registration)")
                return None
        except Exception as e:
            logger.debug(f"Deeplink generation skipped: {str(e)} (not required for QR code scanning)")
            return None
    
    def check_transaction_by_md5(self, md5_hash: str) -> Optional[Dict[str, Any]]:
        """
        Check transaction status using MD5 hash
        
        Args:
            md5_hash: MD5 hash of the QR code string
        
        Returns:
            Transaction data or None if not found/failed
        """
        token = self.get_access_token()
        if not token:
            logger.error("Cannot check transaction: No access token")
            return None
        
        logger.info(f"Checking transaction with MD5: {md5_hash}")
        
        try:
            url = f"{self.base_url}/v1/check_transaction_by_md5"
            payload = {"md5": md5_hash}
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            logger.info(f"Calling Bakong API: {url}")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            logger.info(f"Bakong API status: {response.status_code}")
            logger.info(f"Bakong API response: {response.text}")
            
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Parsed response data: {data}")
            
            if data.get('responseCode') == 0:
                logger.info(f"Transaction found for MD5: {md5_hash}")
                logger.info(f"Transaction details: {data.get('data')}")
                return data.get('data')
            elif data.get('errorCode') == 1:
                logger.debug(f"Transaction not found for MD5: {md5_hash}")
                return None
            else:
                logger.error(f"Transaction check failed: {data.get('responseMessage')}")
                return None
        except Exception as e:
            logger.error(f"Error checking transaction by MD5: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def check_transaction_by_hash(self, transaction_hash: str) -> Optional[Dict[str, Any]]:
        """
        Check transaction status using full transaction hash
        
        Args:
            transaction_hash: Full 64-character transaction hash
        
        Returns:
            Transaction data or None if not found/failed
        """
        token = self.get_access_token()
        if not token:
            logger.error("Cannot check transaction: No access token")
            return None
        
        try:
            url = f"{self.base_url}/v1/check_transaction_by_hash"
            payload = {"hash": transaction_hash}
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('responseCode') == 0:
                logger.info(f"Transaction found for hash: {transaction_hash[:16]}...")
                return data.get('data')
            elif data.get('errorCode') == 1:
                logger.debug(f"Transaction not found for hash: {transaction_hash[:16]}...")
                return None
            else:
                logger.error(f"Transaction check failed: {data.get('responseMessage')}")
                return None
        except Exception as e:
            logger.error(f"Error checking transaction by hash: {str(e)}")
            return None
    
    def check_bakong_account(self, account_id: str) -> bool:
        """
        Check if a Bakong account exists
        
        Args:
            account_id: Bakong account ID (e.g., user@bank)
        
        Returns:
            True if account exists, False otherwise
        """
        token = self.get_access_token()
        if not token:
            logger.error("Cannot check account: No access token")
            return False
        
        try:
            url = f"{self.base_url}/v1/check_bakong_account"
            payload = {"accountId": account_id}
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return data.get('responseCode') == 0
        except Exception as e:
            logger.error(f"Error checking Bakong account: {str(e)}")
            return False
    
    def batch_check_transactions_by_md5(self, md5_list: list) -> Optional[list]:
        """
        Check multiple transactions at once using MD5 hashes
        
        Args:
            md5_list: List of MD5 hashes (max 50)
        
        Returns:
            List of transaction results or None if failed
        """
        if len(md5_list) > 50:
            logger.warning("MD5 list exceeds 50 items, truncating")
            md5_list = md5_list[:50]
        
        token = self.get_access_token()
        if not token:
            logger.error("Cannot check transactions: No access token")
            return None
        
        try:
            url = f"{self.base_url}/v1/check_transaction_by_md5_list"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            response = requests.post(url, json=md5_list, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            if data.get('responseCode') == 0:
                logger.info(f"Batch checked {len(md5_list)} transactions")
                return data.get('data', [])
            else:
                logger.error(f"Batch transaction check failed: {data.get('responseMessage')}")
                return None
        except Exception as e:
            logger.error(f"Error in batch transaction check: {str(e)}")
            return None
