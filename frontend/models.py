from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

KYC_STATUS_CHOICES = (
    ("NOT_SUBMITTED", "Not Submitted"),
    ("PENDING", "Pending"),
    ("APPROVED", "Approved"),
    ("REJECTED", "Rejected"),
)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    profile_picture = models.ImageField(upload_to="profile_pics/", null=True, blank=True)
    full_name = models.CharField(max_length=255)
    age = models.PositiveIntegerField()
    income_source = models.CharField(max_length=255)
    monthly_income = models.DecimalField(max_digits=10, decimal_places=2)
    kyc_verified = models.BooleanField(default=False)
    kyc_status = models.CharField(
        max_length=20, choices=KYC_STATUS_CHOICES, default="NOT_SUBMITTED"
    )
    phone = models.CharField(max_length=20, null=True, blank=True)
    # KYC Documents
    citizenship_front = models.FileField(upload_to="kyc_docs/", null=True, blank=True)
    citizenship_back = models.FileField(upload_to="kyc_docs/", null=True, blank=True)
    selfie = models.FileField(upload_to="kyc_docs/", null=True, blank=True)
    income_proof = models.FileField(upload_to="kyc_docs/", null=True, blank=True)

    # Legacy field - keep for compatibility if needed, but we'll use specific ones
    kyc_document = models.FileField(upload_to="kyc_docs/", null=True, blank=True)

    address = models.TextField()
    aadhaar_number = models.CharField(max_length=50, null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.00, null=True, blank=True
    )
    referral_code = models.CharField(max_length=10, unique=True, null=True, blank=True)
    reward_points = models.IntegerField(default=0)

    @property
    def trust_score(self):
        """Calculate trust score based on various factors"""
        # Start with a base score
        score = 80

        # Penalize for late payments
        late_payments = MoneyTransaction.objects.filter(
            borrower=self.user, status="DEFAULTED"
        ).count()
        score -= late_payments * 20

        # Reward for successful repayments
        successful_repayments = MoneyTransaction.objects.filter(
            borrower=self.user, status="REPAID"
        ).count()
        score += successful_repayments * 5

        # Verification bonus
        if self.kyc_status == "APPROVED":
            score += 10

        # Rating factor
        # If no rating, assume neutral 3.0
        r = float(self.rating) if (self.rating and self.rating > 0) else 3.0
        score += (r - 3) * 5

        return float(max(0, min(100, score)))

    @property
    def total_lends(self):
        """Calculate total successful/active lends"""
        money_lends = self.user.money_lends.exclude(status="PENDING").count()
        goods_lends = self.user.goods_lend_transactions.exclude(
            status="REJECTED"
        ).count()
        return money_lends + goods_lends

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self.generate_referral_code()
        super().save(*args, **kwargs)

    def generate_referral_code(self):
        import random
        import string

        while True:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not UserProfile.objects.filter(referral_code=code).exists():
                return code

    def __str__(self):
        return self.user.username

    @property
    def borrowing_limit(self):
        # Unverified users have a flat limit of 5000
        if self.kyc_status != "APPROVED":
            return Decimal("5000.00")
        return Decimal("10000000.00")  # No limit for verified

    @property
    def lending_limit(self):
        # Unverified users have a flat limit of 5000
        if self.kyc_status != "APPROVED":
            return Decimal("5000.00")
        return Decimal("10000000.00")  # No limit for verified


class FriendRequest(models.Model):
    from_user = models.ForeignKey(
        User, related_name="sent_friend_requests", on_delete=models.CASCADE
    )
    to_user = models.ForeignKey(
        User, related_name="received_friend_requests", on_delete=models.CASCADE
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    accepted = models.BooleanField(default=False)

    class Meta:
        unique_together = ("from_user", "to_user")


class Friendship(models.Model):
    user1 = models.ForeignKey(
        User, related_name="friendships1", on_delete=models.CASCADE
    )
    user2 = models.ForeignKey(
        User, related_name="friendships2", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user1", "user2")


class LoanOffer(models.Model):
    lender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="loan_offers"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2
    )  # Monthly interest
    duration_months = models.PositiveIntegerField(default=1)
    min_trust_score = models.IntegerField(default=0)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Offer by {self.lender.username}: Rs. {self.amount} @ {self.interest_rate}%"


class MoneyTransaction(models.Model):
    TRANSACTION_TYPES = (
        ("LEND", "Lend"),
        ("BORROW", "Borrow"),
    )
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("ACTIVE", "Active"),
        ("REPAID", "Repaid"),
        ("DEFAULTED", "Defaulted"),
    )

    lender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="money_lends"
    )
    borrower = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="money_borrows"
    )
    loan_offer = models.ForeignKey(
        LoanOffer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2
    )  # Annual percentage
    deadline = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")

    # Khalti Integration Fields
    khalti_transaction_id = models.CharField(max_length=100, null=True, blank=True)
    khalti_token = models.CharField(max_length=100, null=True, blank=True)
    payment_status = models.CharField(
        max_length=20, default="NOT_PAID"
    )  # NOT_PAID, INITIATED, COMPLETED, FAILED

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_interest(self):
        # Basic interest calculation logic
        # For simplicity: Total Repayment = Amount + (Amount * InterestRate / 100)
        return self.amount * (1 + self.interest_rate / 100)


class GoodsExchange(models.Model):
    EXCHANGE_TYPES = (
        ("LEND", "Lend"),
        ("BORROW", "Borrow"),
        ("EXCHANGE", "Swap/Exchange"),
        ("RENT", "Rent (Small Fee)"),
    )

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="goods_offered"
    )
    item_name = models.CharField(max_length=255)
    description = models.TextField()
    exchange_type = models.CharField(max_length=20, choices=EXCHANGE_TYPES)
    condition = models.CharField(max_length=100)
    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GoodsTransaction(models.Model):
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("COMPLETED", "Completed"),
        ("RETURNED", "Returned"),
    )

    item = models.ForeignKey(
        GoodsExchange, on_delete=models.CASCADE, related_name="transactions"
    )
    lender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="goods_lend_transactions"
    )
    borrower = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="goods_borrow_transactions"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.item.item_name} transition: {self.lender} to {self.borrower}"


class Referral(models.Model):
    referrer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="referrals_made"
    )
    referred_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="referred_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Review(models.Model):
    reviewer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reviews_given"
    )
    reviewee = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reviews_received"
    )

    # Link to transactions
    money_transaction = models.ForeignKey(
        MoneyTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
    )
    goods_transaction = models.ForeignKey(
        GoodsTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
    )

    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review by {self.reviewer.username} for {self.reviewee.username}"


class ChatMessage(models.Model):
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_messages"
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_messages"
    )
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["timestamp"]


class Notification(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class FineReward(models.Model):
    TYPES = (
        ("FINE", "Fine"),
        ("REWARD", "Reward"),
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="fines_rewards"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    type = models.CharField(max_length=10, choices=TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)


class TrustScore(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="trust_scores"
    )
    score = models.IntegerField()
    reason = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.score}"


class PasswordResetCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        # Code is valid for 10 minutes
        import datetime

        from django.utils import timezone

        return self.created_at >= timezone.now() - datetime.timedelta(minutes=10)


class SignupOTP(models.Model):
    email = models.EmailField()
    code = models.CharField(max_length=6)
    signup_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        import datetime

        from django.utils import timezone

        return self.created_at >= timezone.now() - datetime.timedelta(minutes=10)
