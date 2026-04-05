import base64
import hashlib
import hmac
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class EsewaService:
    def __init__(self):
        self.secret_key = getattr(settings, "ESEWA_SECRET_KEY", "8gBm/:&EnhH.1/q")
        self.product_code = getattr(settings, "ESEWA_PRODUCT_CODE", "EPAYTEST")
        # Test URL: https://rc-epay.esewa.com.np/api/epay/main/v2/form
        # Live URL: https://epay.esewa.com.np/api/epay/main/v2/form
        self.base_url = "https://rc-epay.esewa.com.np/api/epay/main/v2/form"

    def generate_signature(self, total_amount, transaction_uuid, product_code):
        """
        Generate HMAC-SHA256 signature for eSewa EPAY V2
        Format: total_amount,transaction_uuid,product_code
        """
        data = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"

        # Create HMAC SHA256 signature
        secret = bytes(self.secret_key, "utf-8")
        message = bytes(data, "utf-8")

        signature = hmac.new(secret, message, digestmod=hashlib.sha256).digest()

        # Base64 encode the signature
        encoded_signature = base64.b64encode(signature).decode("utf-8")
        return encoded_signature

    def get_payment_payload(self, amount, transaction_uuid, success_url, failure_url):
        """
        Prepare payload for eSewa payment form
        """
        total_amount = str(amount)
        signature = self.generate_signature(
            total_amount, transaction_uuid, self.product_code
        )

        payload = {
            "amount": total_amount,
            "failure_url": failure_url,
            "product_delivery_charge": "0",
            "product_service_charge": "0",
            "product_code": self.product_code,
            "signature": signature,
            "signed_field_names": "total_amount,transaction_uuid,product_code",
            "success_url": success_url,
            "tax_amount": "0",
            "total_amount": total_amount,
            "transaction_uuid": transaction_uuid,
        }
        return payload
