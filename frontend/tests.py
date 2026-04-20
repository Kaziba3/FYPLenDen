import datetime
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    ChatMessage,
    FriendRequest,
    Friendship,
    GoodsExchange,
    GoodsTransaction,
    LoanOffer,
    MoneyTransaction,
    Review,
    SignupOTP,
    UserProfile,
    PasswordResetCode,
)


class LenDenUnitTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Create a base user for tests
        self.user_password = "testpassword123"
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password=self.user_password,
            first_name="Test",
            last_name="User",
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            full_name="Test User",
            age=25,
            income_source="Salary",
            monthly_income=50000,
            address="Kathmandu, Nepal",
            kyc_status="NOT_SUBMITTED",
        )

    def test_ut01_user_registration(self):
        """Register with valid full details including OTP email verification"""
        url = reverse("signup")
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "password": "newpassword123",
            "first_name": "New",
            "last_name": "User",
            "age": 22,
            "income_source": "Business",
            "monthly_income": 40000,
            "address": "Pokhara",
        }
        # Use patch to mock the send_mail function in views.py
        with patch("frontend.views.send_mail") as mocked_mail:
            response = self.client.post(url, data)
            # Expect redirect to verify page
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("signup_verify_otp"), response.url)
            # Check OTP creation
            self.assertTrue(SignupOTP.objects.filter(email="new@example.com").exists())
            # Check email sent
            self.assertTrue(mocked_mail.called)

    def test_ut02_otp_verification(self):
        """Verify signup with a valid 6-digit OTP"""
        otp_code = "123456"
        signup_data = {
            "username": "otpuser",
            "email": "otp@example.com",
            "password": "otppassword123",
            "first_name": "OTP",
            "last_name": "User",
            "age": 30,
            "income_source": "Trading",
            "monthly_income": 60000,
            "address": "Lalitpur",
        }
        SignupOTP.objects.create(
            email="otp@example.com", code=otp_code, signup_data=signup_data
        )

        # Set session
        session = self.client.session
        session["signup_email"] = "otp@example.com"
        session.save()

        url = reverse("signup_verify_otp")
        response = self.client.post(url, {"code": otp_code})

        # Should redirect to kyc_form after success
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("kyc_form"))
        # Verify user created
        self.assertTrue(User.objects.filter(username="otpuser").exists())

    def test_ut03_user_login(self):
        """Login with valid username and password credentials"""
        url = reverse("login")
        response = self.client.post(
            url, {"username": "testuser", "password": self.user_password}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("user_dashboard"))

    def test_ut04_login_invalid_credentials(self):
        """Login attempt with incorrect password"""
        url = reverse("login")
        response = self.client.post(
            url, {"username": "testuser", "password": "wrongpassword"}
        )
        # Should stay on login page or redirect to it
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password")

    def test_ut05_duplicate_username_check(self):
        """Register with a username that already exists in the system"""
        url = reverse("signup")
        data = {
            "username": "testuser",  # Already exists from setUp
            "email": "another@example.com",
            "password": "password123",
        }
        response = self.client.post(url, data)
        self.assertContains(response, "Username is already taken")

    def test_ut06_kyc_form_submission(self):
        """Submit KYC with all required documents"""
        self.client.login(username="testuser", password=self.user_password)
        url = reverse("kyc_submit")
        
        # Mock files
        citizenship_front = SimpleUploadedFile("front.jpg", b"file_content", content_type="image/jpeg")
        citizenship_back = SimpleUploadedFile("back.jpg", b"file_content", content_type="image/jpeg")
        selfie = SimpleUploadedFile("selfie.jpg", b"file_content", content_type="image/jpeg")
        income_proof = SimpleUploadedFile("income.pdf", b"file_content", content_type="application/pdf")

        data = {
            "full_name": "Test User Pro",
            "gender": "Male",
            "phone": "9800000000",
            "address": "KTM",
            "aadhaar": "123456789012",
            "income_source": "Salary",
            "monthly_income": "60000",
            "id_document": citizenship_front,
            "citizenship_back": citizenship_back,
            "selfie": selfie,
            "income_proof": income_proof,
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify profile updated
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.kyc_status, "PENDING")
        self.assertFalse(self.profile.kyc_verified)

    def test_ut07_borrowing_limit_enforcement(self):
        """Attempt to borrow an amount exceeding the limit (Rs. 5000 for unverified)"""
        self.client.login(username="testuser", password=self.user_password)
        # Create a lender and offer
        lender = User.objects.create_user(username="lender", password="password")
        offer = LoanOffer.objects.create(
            lender=lender, amount=6000, interest_rate=2, duration_months=3
        )
        
        url = reverse("borrow_offer", kwargs={"offer_id": offer.id})
        response = self.client.post(url)
        
        # Should redirect back with error message
        self.assertEqual(response.status_code, 302)
        # Check messages (using session since it's a redirect)
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any("exceeds your borrowing limit" in str(m) for m in messages))

    def test_ut20_referral_code_generation(self):
        """Profile is saved and a unique referral code is auto-generated"""
        # Referral code is generated in setUp which calls save()
        self.assertIsNotNone(self.profile.referral_code)
        self.assertEqual(len(self.profile.referral_code), 8)
        self.assertTrue(self.profile.referral_code.isalnum())

    def test_ut08_loan_offer_creation(self):
        """Post a new loan offer and check listing"""
        self.profile.kyc_status = "APPROVED" # Must be verified to lend
        self.profile.save()
        self.client.login(username="testuser", password=self.user_password)
        url = reverse("lend")
        data = {
            "action": "post_offer",
            "amount": "10000",
            "interest_rate": "1.5",
            "duration": "6",
            "min_trust_score": "85",
            "description": "Business loan",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(LoanOffer.objects.filter(amount=10000).exists())

    def test_ut09_duplicate_active_borrow_prevention(self):
        """Attempt a second borrow while one is still active"""
        self.client.login(username="testuser", password=self.user_password)
        lender = User.objects.create_user(username="lender2", password="password")
        # Create an active loan first
        MoneyTransaction.objects.create(
            lender=lender, borrower=self.user, amount=1000, interest_rate=12,
            deadline=datetime.date.today() + datetime.timedelta(days=30),
            status="ACTIVE"
        )
        
        # Now try to borrow again from another offer
        offer = LoanOffer.objects.create(lender=lender, amount=2000, interest_rate=2, duration_months=1)
        url = reverse("borrow_offer", kwargs={"offer_id": offer.id})
        response = self.client.post(url)
        
        # Should be blocked
        self.assertEqual(response.status_code, 302)
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any("already have an active borrowing" in str(m) for m in messages))

    def test_ut10_esewa_payment_initiation(self):
        """Lender approves and eSewa payment flow is triggered"""
        self.client.login(username="testuser", password=self.user_password)
        borrower = User.objects.create_user(username="borrower2", password="password")
        tx = MoneyTransaction.objects.create(
            lender=self.user, borrower=borrower, amount=5000, interest_rate=12,
            deadline=datetime.date.today() + datetime.timedelta(days=30),
            status="PENDING"
        )
        
        url = reverse("esewa_initiate", kwargs={"transaction_id": tx.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "esewa.com") # Redirection form content

    def test_ut11_esewa_callback_loan_activation(self):
        """eSewa returns COMPLETE status after successful payment"""
        self.client.login(username="testuser", password=self.user_password)
        borrower = User.objects.create_user(username="borrower3", password="password")
        tx = MoneyTransaction.objects.create(
            lender=self.user, borrower=borrower, amount=5000, interest_rate=12,
            deadline=datetime.date.today() + datetime.timedelta(days=30),
            status="PENDING"
        )
        
        # Simulate eSewa callback payload
        import base64
        import json
        payload = {
            "transaction_uuid": f"{tx.id}-unique",
            "status": "COMPLETE",
            "transaction_code": "ESEWA_CODE_123"
        }
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        
        url = reverse("esewa_callback") + f"?data={encoded}"
        response = self.client.get(url)
        
        tx.refresh_from_db()
        self.assertEqual(tx.status, "ACTIVE")
        self.assertEqual(tx.payment_status, "COMPLETED")

    def test_ut12_loan_repayment_with_overdue_fine(self):
        """Borrower repays a loan that is past its deadline"""
        self.client.login(username="testuser", password=self.user_password)
        lender = User.objects.create_user(username="lender3", password="password")
        # Creating a loan that expired yesterday
        tx = MoneyTransaction.objects.create(
            lender=lender, borrower=self.user, amount=1000, interest_rate=12,
            deadline=datetime.date.today() - datetime.timedelta(days=1),
            status="ACTIVE"
        )
        
        url = reverse("esewa_repayment_initiate", kwargs={"transaction_id": tx.id})
        response = self.client.get(url)
        
        # Check if fine was calculated (1000 + 10% annual interest (~10) + 5% fine (50))
        # interest_rate in DB is annual, so 1% of 1000 = 10. (1120 total, then 5% fine of 1120 = 56)
        # Total should be 1176
        self.assertContains(response, "1176")
        
    def test_ut13_trust_score_calculation(self):
        """Calculate trust score based on mix of repaid and defaulted transactions"""
        # Base is 80
        # +1 successfully repaid (+5 each)
        # +1 defaulted (-20 each)
        # +1 kyc approved (+10)
        # +1 rating of 4.0 ((4-3)*5 = +5)
        # Total should be 80 + 5 - 20 + 10 + 5 = 80
        
        lender = User.objects.create_user(username="lender4", password="password")
        MoneyTransaction.objects.create(
            lender=lender, borrower=self.user, amount=1000, interest_rate=12,
            deadline=datetime.date.today(), status="REPAID"
        )
        MoneyTransaction.objects.create(
            lender=lender, borrower=self.user, amount=1000, interest_rate=12,
            deadline=datetime.date.today(), status="DEFAULTED"
        )
        
        self.profile.kyc_status = "APPROVED"
        self.profile.rating = Decimal("4.0")
        self.profile.save()
        
        self.assertEqual(self.profile.trust_score, 80.0)

    def test_ut14_goods_listing_creation(self):
        """Owner lists a new item for lending/exchange"""
        self.client.login(username="testuser", password=self.user_password)
        url = reverse("goods")
        data = {
            "item_name": "Mountain Bike",
            "description": "Trail bike for rent",
            "exchange_type": "RENT",
            "condition": "Good",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(GoodsExchange.objects.filter(item_name="Mountain Bike").exists())

    def test_ut15_goods_exchange_request(self):
        """User requests an exchange for an available listing"""
        self.client.login(username="testuser", password=self.user_password)
        owner = User.objects.create_user(username="owner1", password="password")
        item = GoodsExchange.objects.create(
            owner=owner, item_name="Tent", description="4-person tent", 
            exchange_type="LEND", condition="New", available=True
        )
        
        url = reverse("request_exchange", kwargs={"item_id": item.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(GoodsTransaction.objects.filter(item=item, borrower=self.user).exists())

    def test_ut16_friend_request_sending(self):
        """User sends a friend request to another registered user"""
        self.client.login(username="testuser", password=self.user_password)
        other = User.objects.create_user(username="friend1", password="password")
        url = reverse("friends")
        data = {
            "action": "add",
            "username": "friend1",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(FriendRequest.objects.filter(from_user=self.user, to_user=other).exists())

    def test_ut17_password_reset_via_otp(self):
        """User initiates password reset and receives code"""
        url = reverse("forgot_password")
        with patch("frontend.views.send_mail") as mocked_mail:
            response = self.client.post(url, {"email": "test@example.com"})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(PasswordResetCode.objects.filter(user=self.user).exists())
            self.assertTrue(mocked_mail.called)

    def test_ut18_review_submission(self):
        """User submits a rating and comment after transaction"""
        self.client.login(username="testuser", password=self.user_password)
        reviewee = User.objects.create_user(username="reviewee1", password="password")
        UserProfile.objects.create(user=reviewee, full_name="Rev User", age=20, monthly_income=0, address="X")
        
        url = reverse("submit_review")
        data = {
            "reviewee_id": reviewee.id,
            "rating": "5",
            "comment": "Excellent experience",
            "transaction_type": "MONEY",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Review.objects.filter(reviewer=self.user, reviewee=reviewee).exists())
        
        # Verify reviewee's rating updated
        reviewee.profile.refresh_from_db()
        self.assertEqual(reviewee.profile.rating, Decimal("5.00"))

    def test_ut19_real_time_chat_message(self):
        """User sends a message (testing storage logic)"""
        self.client.login(username="testuser", password=self.user_password)
        receiver = User.objects.create_user(username="chatuser", password="password")
        
        url = reverse("chat") + f"?user_id={receiver.id}"
        data = {"content": "Hello there!"}
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ChatMessage.objects.filter(sender=self.user, receiver=receiver, message="Hello there!").exists())



