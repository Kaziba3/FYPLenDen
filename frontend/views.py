import base64
import datetime
import json
import logging
import random
import string
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Avg, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import (
    ChatMessage,
    FineReward,
    FriendRequest,
    Friendship,
    GoodsExchange,
    GoodsTransaction,
    LoanOffer,
    MoneyTransaction,
    Notification,
    PasswordResetCode,
    Review,
    SignupOTP,
    UserProfile,
)
from .utils.esewa import EsewaService

logger = logging.getLogger(__name__)


def landing_page(request):
    """Landing page view"""
    # If user is authenticated, redirect to dashboard
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("admin_dashboard")
        else:
            return redirect("user_dashboard")

    # Show landing page for unauthenticated users
    return render(request, "landing.html", {"hide_nav": True})


def login_view(request):
    """Login view"""
    if request.user.is_authenticated:
        return redirect("user_dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            if user.is_superuser:
                return redirect("admin_dashboard")
            else:
                return redirect("user_dashboard")
        else:
            messages.error(request, "Invalid username or password.", extra_tags="auth")

    return render(request, "auth/login.html", {"hide_nav": True})


def signup_view(request):
    """Signup view with OTP verification"""
    if request.user.is_authenticated:
        return redirect("user_dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username is already taken.", extra_tags="auth")
            return render(request, "auth/signup.html", {"hide_nav": True})

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email is already registered.", extra_tags="auth")
            return render(request, "auth/signup.html", {"hide_nav": True})

        # Instead of creating user, send OTP
        code = "".join(random.choices(string.digits, k=6))

        signup_data = {
            "username": username,
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
            "referral_code": request.POST.get("referral_code"),
            "age": request.POST.get("age", 18),
            "income_source": request.POST.get("income_source", "None"),
            "monthly_income": request.POST.get("monthly_income", 0),
            "address": request.POST.get("address", ""),
        }

        SignupOTP.objects.create(email=email, code=code, signup_data=signup_data)

        # Send email
        subject = "Verify your LenDen Account"
        message = f"Hello {username},\n\nYour verification code for signup is: {code}\n\nThis code will expire in 10 minutes."
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [email]

        try:
            send_mail(subject, message, from_email, recipient_list)
            request.session["signup_email"] = email
            messages.success(request, "Verification code sent to your email.")
            return redirect("signup_verify_otp")
        except Exception as e:
            messages.error(request, f"Error sending email: {str(e)}", extra_tags="auth")

    return render(request, "auth/signup.html", {"hide_nav": True})


def signup_verify_otp(request):
    """Verify OTP and complete signup"""
    email = request.session.get("signup_email")
    if not email:
        return redirect("signup")

    if request.method == "POST":
        code = request.POST.get("code")
        otp_record = (
            SignupOTP.objects.filter(email=email, code=code)
            .order_by("-created_at")
            .first()
        )

        if otp_record and otp_record.is_valid():
            signup_data = otp_record.signup_data

            try:
                user = User.objects.create_user(
                    username=signup_data["username"],
                    email=signup_data["email"],
                    password=signup_data["password"],
                    first_name=signup_data["first_name"],
                    last_name=signup_data["last_name"],
                )

                # Referral logic
                referrer_code = signup_data.get("referral_code")
                referrer_profile = None
                if referrer_code:
                    referrer_profile = UserProfile.objects.filter(
                        referral_code=referrer_code
                    ).first()

                # Create UserProfile
                profile = UserProfile.objects.create(
                    user=user,
                    full_name=f"{signup_data['first_name']} {signup_data['last_name']}",
                    age=signup_data.get("age", 18),
                    income_source=signup_data.get("income_source", "None"),
                    monthly_income=signup_data.get("monthly_income", 0),
                    address=signup_data.get("address", ""),
                    kyc_status="NOT_SUBMITTED",
                )

                if referrer_profile:
                    referrer_profile.reward_points += 100
                    referrer_profile.save()
                    profile.reward_points += 50
                    profile.save()
                    messages.success(
                        request,
                        f"Referral bonus applied! You got 50 points and {referrer_profile.user.username} got 100 points.",
                        extra_tags="auth",
                    )

                auth_login(request, user)
                messages.success(
                    request,
                    "Account verified and created successfully! Please complete KYC verification.",
                    extra_tags="auth",
                )

                # Clear session and OTP record
                del request.session["signup_email"]
                otp_record.delete()

                return redirect("kyc_form")
            except Exception as e:
                messages.error(
                    request, f"Error creating account: {str(e)}", extra_tags="auth"
                )
        else:
            messages.error(request, "Invalid or expired verification code.")

    return render(
        request,
        "auth/verify_code.html",
        {
            "hide_nav": True,
            "email": email,
            "action_url": "signup_verify_otp",
            "title": "Verify Signup",
        },
    )


def logout_view(request):
    """Logout view"""
    auth_logout(request)
    return redirect("landing_page")


@login_required
def kyc_form(request):
    """KYC form consolidated view"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    if request.user.profile.kyc_status == "APPROVED":
        messages.info(request, "Your KYC is already verified.", extra_tags="kyc")
        return redirect("user_dashboard")

    if request.user.profile.kyc_status == "PENDING":
        messages.info(request, "Your KYC is under review.", extra_tags="kyc")
        return redirect("user_dashboard")

    return render(request, "auth/kyc_form.html")


@login_required
def kyc_submit(request):
    """Handle consolidated KYC submission"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    if request.method == "POST":
        profile = request.user.profile

        # Personal Info
        dob = request.POST.get("dob")
        if dob:
            try:
                birth_date = datetime.datetime.strptime(dob, "%Y-%m-%d").date()
                today = datetime.date.today()
                profile.age = (
                    today.year
                    - birth_date.year
                    - ((today.month, today.day) < (birth_date.month, birth_date.day))
                )
            except ValueError:
                pass

        profile.full_name = request.POST.get("full_name", profile.full_name)
        profile.gender = request.POST.get("gender", profile.gender)
        profile.phone = request.POST.get("phone", profile.phone)
        profile.address = request.POST.get("address", profile.address)
        profile.aadhaar_number = request.POST.get("aadhaar", profile.aadhaar_number)

        # Employment & Income
        profile.income_source = request.POST.get("income_source", profile.income_source)
        income_val = request.POST.get("monthly_income")
        if income_val:
            try:
                profile.monthly_income = float(income_val)
            except ValueError:
                pass

        # Document Uploads - Updated to match form field names
        if "id_document" in request.FILES:
            profile.citizenship_front = request.FILES["id_document"]
            profile.kyc_document = request.FILES["id_document"]  # Sync legacy field
        if "citizenship_back" in request.FILES:
            profile.citizenship_back = request.FILES["citizenship_back"]
        if "selfie" in request.FILES:
            profile.selfie = request.FILES["selfie"]
        if "income_proof" in request.FILES:
            profile.income_proof = request.FILES["income_proof"]

        profile.kyc_status = "PENDING"
        profile.kyc_verified = False  # Ensure review is needed
        profile.save()

        messages.success(
            request,
            "KYC submitted successfully! It will be reviewed within 24 hours.",
            extra_tags="kyc",
        )
        return redirect("user_dashboard")

    return redirect("kyc_form")


# User Views
@login_required
def user_dashboard(request):
    """User dashboard view"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    profile = request.user.profile

    # Financial Stats
    active_borrows = MoneyTransaction.objects.filter(
        borrower=request.user, status="ACTIVE"
    )
    active_lendings = MoneyTransaction.objects.filter(
        lender=request.user, status="ACTIVE"
    )

    active_borrows_amount = sum(tx.amount for tx in active_borrows)
    active_lendings_amount = sum(tx.amount for tx in active_lendings)

    # Borrowing Power
    borrow_limit = profile.borrowing_limit
    usage_percent = (
        (active_borrows_amount / borrow_limit * 100) if borrow_limit > 0 else 0
    )

    # Recent Transactions (last 5)
    recent_transactions = MoneyTransaction.objects.filter(
        Q(lender=request.user) | Q(borrower=request.user)
    ).order_by("-created_at")[:5]

    # Transform transactions for current user context
    tx_list = []
    for tx in recent_transactions:
        other_user = tx.borrower if tx.lender == request.user else tx.lender
        tx_type = "Lent to" if tx.lender == request.user else "Borrowed from"
        tx_list.append(
            {
                "date": tx.created_at.date(),
                "other_user": other_user,
                "type": f"{tx_type} {other_user.username}",
                "amount": tx.amount,
                "status": tx.status,
            }
        )

    # Social Stats
    friends_count = Friendship.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).count()

    # Notifications
    notifications = Notification.objects.filter(user=request.user).order_by(
        "-created_at"
    )[:5]

    # Pending Lend Requests (Needs Approval/Funding)
    pending_lend_requests = MoneyTransaction.objects.filter(
        lender=request.user, status="PENDING"
    )

    context = {
        "profile": profile,
        "active_borrows_amount": active_borrows_amount,
        "active_borrows_count": active_borrows.count(),
        "active_lendings_amount": active_lendings_amount,
        "active_lendings_count": active_lendings.count(),
        "borrow_limit": borrow_limit,
        "usage_percent": usage_percent,
        "recent_transactions": tx_list,
        "notifications": notifications,
        "friends_count": friends_count,
        "pending_lend_requests": pending_lend_requests,
    }
    return render(request, "user/dashboard.html", context)


@login_required
def marketplace(request):
    """Marketplace view showing active loan offers"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    # Filter active loan offers from others
    loan_offers = LoanOffer.objects.filter(is_active=True).exclude(lender=request.user)

    # Apply filters
    min_amount = request.GET.get("min_amount")
    max_amount = request.GET.get("max_amount")
    max_interest = request.GET.get("max_interest")

    if min_amount:
        loan_offers = loan_offers.filter(amount__gte=Decimal(min_amount))
    if max_amount:
        loan_offers = loan_offers.filter(amount__lte=Decimal(max_amount))
    if max_interest:
        loan_offers = loan_offers.filter(interest_rate__lte=Decimal(max_interest))

    # Prepare Map Data (Lenders, Borrowers, Goods)
    map_data = []

    # 1. Active Loan Offers
    for offer in loan_offers:
        profile = offer.lender.profile
        if profile.latitude and profile.longitude:
            map_data.append(
                {
                    "id": profile.user.id,
                    "username": profile.user.username,
                    "lat": float(profile.latitude),
                    "lng": float(profile.longitude),
                    "rating": float(profile.rating),
                    "type": "loan_offer",
                    "amount": float(offer.amount),
                    "label": f"Loan: Rs. {offer.amount}",
                }
            )

    # 2. Goods for Exchange/Lending
    goods_items = GoodsExchange.objects.filter(available=True).exclude(
        owner=request.user
    )
    for item in goods_items:
        profile = item.owner.profile
        if profile.latitude and profile.longitude:
            map_data.append(
                {
                    "id": profile.user.id,
                    "username": profile.user.username,
                    "lat": float(profile.latitude),
                    "lng": float(profile.longitude),
                    "rating": float(profile.rating),
                    "type": "goods",
                    "item_name": item.item_name,
                    "label": f"Goods: {item.item_name}",
                }
            )

    # 3. Pending Borrow Requests (Nearby needs)
    borrow_requests = MoneyTransaction.objects.filter(status="PENDING").exclude(
        borrower=request.user
    )
    for req in borrow_requests:
        profile = req.borrower.profile
        if profile.latitude and profile.longitude:
            map_data.append(
                {
                    "id": profile.user.id,
                    "username": profile.user.username,
                    "lat": float(profile.latitude),
                    "lng": float(profile.longitude),
                    "rating": float(profile.rating),
                    "type": "borrow_request",
                    "amount": float(req.amount),
                    "label": f"Request: Rs. {req.amount}",
                }
            )

    context = {"loan_offers": loan_offers, "filters": request.GET, "map_data": map_data}
    return render(request, "user/marketplace.html", context)


@login_required
def borrow(request, offer_id=None):
    """Borrow view - request a loan from an offer or general request"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    profile = request.user.profile
    offer = None
    if offer_id:
        offer = get_object_or_404(LoanOffer, id=offer_id, is_active=True)

    if request.method == "POST":
        if not offer:
            lender_id = request.POST.get("lender_id")
            lender = get_object_or_404(User, id=lender_id)
            amount = Decimal(request.POST.get("amount"))
            interest_rate = Decimal(request.POST.get("interest_rate"))
            duration_months = int(request.POST.get("duration_months", 1))
        else:
            lender = offer.lender
            amount = offer.amount
            interest_rate = offer.interest_rate
            duration_months = offer.duration_months

        # Check borrowing limit
        active_borrows = MoneyTransaction.objects.filter(
            borrower=request.user, status="ACTIVE"
        )
        if active_borrows.exists():
            messages.error(
                request,
                "You already have an active borrowing. Pay it back to borrow again.",
            )
            return redirect("transactions")

        if amount > profile.borrowing_limit:
            messages.error(
                request,
                f"Amount exceeds your borrowing limit of {profile.borrowing_limit}",
            )
            return redirect("marketplace")

        deadline = datetime.date.today() + datetime.timedelta(days=duration_months * 30)

        transaction = MoneyTransaction.objects.create(
            lender=lender,
            borrower=request.user,
            loan_offer=offer,
            amount=amount,
            interest_rate=interest_rate * 12,  # Convert monthly to annual for DB
            deadline=deadline,
            status="PENDING",
        )

        # Notify lender
        Notification.objects.create(
            user=lender,
            message=f"{request.user.username} has requested the loan offer of Rs. {amount} from you.",
        )

        messages.success(
            request, "Loan request sent successfully! Lender needs to approve it."
        )
        return redirect("transactions")

    # If GET
    if offer:
        return render(
            request, "user/borrow_confirm.html", {"offer": offer, "profile": profile}
        )

    potential_lenders = UserProfile.objects.filter(kyc_verified=True).exclude(
        user=request.user
    )
    return render(
        request, "user/borrow.html", {"lenders": potential_lenders, "profile": profile}
    )


@login_required
def lend(request):
    """Lend view - post manual offer or manage requests"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    profile = request.user.profile

    if request.method == "POST":
        action = request.POST.get("action", "post_offer")

        if action == "post_offer":
            amount_str = request.POST.get("amount")
            interest_rate_str = request.POST.get("interest_rate")
            duration_str = request.POST.get("duration")
            min_trust_str = request.POST.get("min_trust_score")

            if not amount_str or not interest_rate_str or not duration_str:
                messages.error(request, "Required fields are missing.")
                return redirect("lend")

            amount = Decimal(amount_str)
            interest_rate = Decimal(interest_rate_str)
            duration = int(duration_str)
            min_trust = int(min_trust_str or 0)
            description = request.POST.get("description", "")

            # Check lending limit
            if amount > profile.lending_limit:
                messages.error(
                    request,
                    f"Amount exceeds your lending limit of {profile.lending_limit}",
                )
                return redirect("lend")

            LoanOffer.objects.create(
                lender=request.user,
                amount=amount,
                interest_rate=interest_rate,
                duration_months=duration,
                min_trust_score=min_trust,
                description=description,
            )
            messages.success(request, "Loan offer posted to marketplace successfully!")
            return redirect("marketplace")

        elif action == "approve_request":
            request_id = request.POST.get("request_id")
            transaction = get_object_or_404(
                MoneyTransaction, id=request_id, lender=request.user, status="PENDING"
            )

            # Hide the offer from marketplace IMMEDIATELY
            if transaction.loan_offer:
                transaction.loan_offer.is_active = False
                transaction.loan_offer.save()

            # We'll mark it as INITIATED and redirect to payment
            return redirect("esewa_initiate", transaction_id=transaction.id)

        elif action == "delete_offer":
            offer_id = request.POST.get("offer_id")
            offer = get_object_or_404(LoanOffer, id=offer_id, lender=request.user)
            offer.delete()
            messages.success(request, "Loan offer deleted successfully.")
            return redirect("lend")

    # GET: Show form and my pending requests
    pending_requests = MoneyTransaction.objects.filter(
        lender=request.user, status="PENDING"
    )
    active_offers = LoanOffer.objects.filter(lender=request.user, is_active=True)

    context = {
        "pending_requests": pending_requests,
        "active_offers": active_offers,
        "profile": profile,
    }
    return render(request, "user/lend.html", context)


@login_required
def goods(request):
    """Goods Hub view (Lend, Borrow, Exchange)"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    if request.method == "POST":
        item_name = request.POST.get("item_name")
        description = request.POST.get("description")
        exchange_type = request.POST.get("exchange_type")
        condition = request.POST.get("condition")

        GoodsExchange.objects.create(
            owner=request.user,
            item_name=item_name,
            description=description,
            exchange_type=exchange_type,
            condition=condition,
        )
        messages.success(
            request, f"Item listed for {exchange_type.lower()} successfully!"
        )
        return redirect("goods")

    # Filter available goods from others
    available_goods = GoodsExchange.objects.filter(available=True).exclude(
        owner=request.user
    )
    my_goods = GoodsExchange.objects.filter(owner=request.user)

    context = {
        "available_goods": available_goods,
        "my_goods": my_goods,
    }
    return render(request, "user/goods.html", context)


@login_required
def request_exchange(request, item_id):
    """Request a good from the marketplace"""
    item = get_object_or_404(GoodsExchange, id=item_id, available=True)
    if item.owner == request.user:
        messages.error(request, "You cannot request your own item.")
        return redirect("goods")

    # Check if already requested
    existing = GoodsTransaction.objects.filter(
        item=item, borrower=request.user, status="PENDING"
    ).exists()
    if existing:
        messages.warning(request, "You have already requested this item.")
        return redirect("goods")

    GoodsTransaction.objects.create(
        item=item, lender=item.owner, borrower=request.user, status="PENDING"
    )

    Notification.objects.create(
        user=item.owner,
        message=f"{request.user.username} has requested your item: {item.item_name}",
    )

    messages.success(request, f"Request for {item.item_name} sent successfully!")
    return redirect("my_exchanges")


@login_required
def manage_exchange(request, transaction_id):
    """Approve or reject an exchange request"""
    transaction = get_object_or_404(
        GoodsTransaction, id=transaction_id, lender=request.user
    )
    action = request.POST.get("action")

    if action == "approve":
        transaction.status = "APPROVED"
        transaction.save()
        # Mark item as unavailable
        transaction.item.available = False
        transaction.item.save()
        Notification.objects.create(
            user=transaction.borrower,
            message=f"Your request for {transaction.item.item_name} is approved by {request.user.username}!",
        )
        messages.success(request, "Exchange request approved.")
    elif action == "reject":
        transaction.status = "REJECTED"
        transaction.save()
        Notification.objects.create(
            user=transaction.borrower,
            message=f"Your request for {transaction.item.item_name} was rejected.",
        )
        messages.info(request, "Exchange request rejected.")

    return redirect("my_exchanges")


@login_required
def complete_exchange(request, transaction_id):
    """Mark exchange as completed or returned"""
    transaction = get_object_or_404(GoodsTransaction, id=transaction_id)
    # Either lender or borrower can mark as complete depending on the stage
    # But usually borrower marks as COMPLETED (received) and lender marks as RETURNED (received back)

    if request.user not in [transaction.lender, transaction.borrower]:
        return HttpResponseForbidden()

    action = request.POST.get("action")
    if action == "complete":  # Borrower confirms receipt
        if transaction.borrower == request.user and transaction.status == "APPROVED":
            transaction.status = "COMPLETED"
            transaction.save()
            messages.success(
                request, "Exchange marked as completed! Please rate the user."
            )
        else:
            messages.error(request, "Invalid action.")

    elif action == "return":  # Lender confirms return
        if transaction.lender == request.user and transaction.status == "COMPLETED":
            transaction.status = "RETURNED"
            transaction.save()
            # Make item available again
            transaction.item.available = True
            transaction.item.save()
            messages.success(request, "Item marked as returned! Please rate the user.")
        else:
            messages.error(request, "Invalid action.")

    return redirect("my_exchanges")


@login_required
def my_exchanges(request):
    """List user's goods transactions"""
    my_requests = GoodsTransaction.objects.filter(borrower=request.user).order_by(
        "-created_at"
    )
    incoming_requests = GoodsTransaction.objects.filter(lender=request.user).order_by(
        "-created_at"
    )

    context = {
        "my_requests": my_requests,
        "incoming_requests": incoming_requests,
    }
    return render(request, "user/goods_transactions.html", context)


@login_required
def friends(request):
    """Friends view with user search"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    query = request.GET.get("q", "")
    search_results = []
    if query:
        search_results = (
            User.objects.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
            )
            .exclude(id=request.user.id)
            .exclude(is_superuser=True)[:10]
        )

    # Handle friend requests
    if request.method == "POST":
        action = request.POST.get("action")
        target_username = request.POST.get("username")
        target_user = get_object_or_404(User, username=target_username)

        if action == "add":
            FriendRequest.objects.get_or_create(
                from_user=request.user, to_user=target_user
            )
            messages.success(request, f"Friend request sent to {target_username}")
        elif action == "accept":
            fr = get_object_or_404(
                FriendRequest, from_user=target_user, to_user=request.user
            )
            fr.accepted = True
            fr.save()
            Friendship.objects.get_or_create(user1=request.user, user2=target_user)
            messages.success(request, f"You are now friends with {target_username}")
        elif action == "reject":
            FriendRequest.objects.filter(
                from_user=target_user, to_user=request.user
            ).delete()
            messages.success(
                request, f"Friend request from {target_username} rejected."
            )
        elif action == "remove":
            Friendship.objects.filter(
                (Q(user1=request.user) & Q(user2=target_user))
                | (Q(user1=target_user) & Q(user2=request.user))
            ).delete()
            # Also delete any friend requests between them to allow a fresh start
            FriendRequest.objects.filter(
                (Q(from_user=request.user) & Q(to_user=target_user))
                | (Q(from_user=target_user) & Q(to_user=request.user))
            ).delete()
            messages.success(request, f"Removed {target_username} from your network.")

        return redirect("friends")

    # Get friends and pending requests
    friends1 = Friendship.objects.filter(user1=request.user).values_list(
        "user2", flat=True
    )
    friends2 = Friendship.objects.filter(user2=request.user).values_list(
        "user1", flat=True
    )
    friend_ids = list(friends1) + list(friends2)
    my_friends = User.objects.filter(id__in=friend_ids)

    pending_requests = FriendRequest.objects.filter(
        to_user=request.user, accepted=False
    )

    context = {
        "friends": my_friends,
        "pending_requests": pending_requests,
        "search_results": search_results,
        "query": query,
    }
    return render(request, "user/friends.html", context)


@login_required
def submit_review(request):
    """Submit a review for another user after a transaction"""
    if request.method == "POST":
        reviewee_id = request.POST.get("reviewee_id")
        rating = request.POST.get("rating")
        comment = request.POST.get("comment")

        transaction_type = request.POST.get("transaction_type")  # 'MONEY' or 'GOODS'
        transaction_id = request.POST.get("transaction_id")

        reviewee = get_object_or_404(User, id=reviewee_id)

        review = Review.objects.create(
            reviewer=request.user,
            reviewee=reviewee,
            rating=int(rating),
            comment=comment,
        )

        if transaction_type == "MONEY" and transaction_id:
            review.money_transaction_id = transaction_id
            review.save()
        elif transaction_type == "GOODS" and transaction_id:
            review.goods_transaction_id = transaction_id
            review.save()

        # Update user's aggregate rating
        all_reviews = Review.objects.filter(reviewee=reviewee)
        avg_rating = sum(r.rating for r in all_reviews) / all_reviews.count()
        profile = reviewee.profile
        profile.rating = avg_rating

        # Reward points based on rating (Task 6)
        points_awarded = 0
        r_val = int(rating)
        if r_val == 5:
            points_awarded = 20
        elif r_val == 4:
            points_awarded = 10
        elif r_val == 3:
            points_awarded = 5

        if points_awarded > 0:
            profile.reward_points += points_awarded
            FineReward.objects.create(
                user=reviewee,
                amount=points_awarded,
                type="REWARD",
                reason=f"Received a {rating}-star rating from {request.user.username}",
            )

        profile.save()

        messages.success(
            request,
            f"Review for {reviewee.username} submitted! {points_awarded} reward points added to their profile.",
        )

        if transaction_type == "MONEY":
            return redirect("transactions")
        elif transaction_type == "GOODS":
            return redirect("my_exchanges")
        return redirect("reviews")

    return redirect("user_dashboard")


@login_required
def reviews(request):
    """View reviews for the current user or a specific user"""
    user_id = request.GET.get("user_id")
    if user_id:
        target_user = get_object_or_404(User, id=user_id)
    else:
        target_user = request.user

    received_reviews = Review.objects.filter(reviewee=target_user).order_by(
        "-timestamp"
    )
    given_reviews = Review.objects.filter(reviewer=target_user).order_by("-timestamp")

    return render(
        request,
        "user/reviews.html",
        {
            "target_user": target_user,
            "received_reviews": received_reviews,
            "given_reviews": given_reviews,
        },
    )


@login_required
def chat(request):
    """Refined chat view with sidebar and active chat context"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    active_user_id = request.GET.get("user_id")

    # 1. Get all users the current user has interacted with
    sent_ids = ChatMessage.objects.filter(sender=request.user).values_list(
        "receiver", flat=True
    )
    received_ids = ChatMessage.objects.filter(receiver=request.user).values_list(
        "sender", flat=True
    )
    f1 = Friendship.objects.filter(user1=request.user).values_list("user2", flat=True)
    f2 = Friendship.objects.filter(user2=request.user).values_list("user1", flat=True)

    partner_ids = set(list(sent_ids) + list(received_ids) + list(f1) + list(f2))
    chat_partners = User.objects.filter(id__in=partner_ids).distinct()

    # 2. Build conversation list for sidebar
    conversations = []
    for partner in chat_partners:
        last_msg = (
            ChatMessage.objects.filter(
                (Q(sender=request.user) & Q(receiver=partner))
                | (Q(sender=partner) & Q(receiver=request.user))
            )
            .order_by("-timestamp")
            .first()
        )

        unread_count = ChatMessage.objects.filter(
            sender=partner, receiver=request.user, is_read=False
        ).count()

        conversations.append(
            {
                "other_user": partner,
                "last_message": {
                    "content": last_msg.message if last_msg else "No messages yet",
                    "timestamp": last_msg.timestamp if last_msg else None,
                },
                "unread_count": unread_count,
            }
        )

    # Sort conversations by last message timestamp (using aware datetime for comparison)
    aware_min = timezone.make_aware(datetime.datetime.min)
    conversations.sort(
        key=lambda x: x["last_message"]["timestamp"] or aware_min, reverse=True
    )

    active_chat = False
    active_chat_user = None
    messages_list = []
    status_alert = None

    if active_user_id:
        active_chat_user = get_object_or_404(User, id=active_user_id)
        active_chat = True

        # Handle message sending
        if request.method == "POST":
            content = request.POST.get("content")
            if content:
                ChatMessage.objects.create(
                    sender=request.user, receiver=active_chat_user, message=content
                )
                return redirect(f"{reverse('chat')}?user_id={active_user_id}")

        # Mark messages as read
        ChatMessage.objects.filter(
            sender=active_chat_user, receiver=request.user, is_read=False
        ).update(is_read=True)

        # Get message history
        messages_raw = ChatMessage.objects.filter(
            (Q(sender=request.user) & Q(receiver=active_chat_user))
            | (Q(sender=active_chat_user) & Q(receiver=request.user))
        ).order_by("timestamp")

        for m in messages_raw:
            messages_list.append(
                {"sender": m.sender, "message": m.message, "timestamp": m.timestamp}
            )

        # Check if friend for alert
        is_friend = Friendship.objects.filter(
            (Q(user1=request.user) & Q(user2=active_chat_user))
            | (Q(user1=active_chat_user) & Q(user2=request.user))
        ).exists()

        if not is_friend:
            status_alert = (
                "Do you know this person? Be cautious when dealing with strangers."
            )

    context = {
        "conversations": conversations,
        "active_chat": active_chat,
        "active_chat_user": active_chat_user,
        "active_user_id": int(active_user_id) if active_user_id else None,
        "chat_messages": messages_list,
        "status_alert": status_alert,
    }
    return render(request, "user/chat.html", context)


@login_required
def get_messages(request, user_id):
    """Fetch new messages for a specific conversation via AJAX"""
    other_user = get_object_or_404(User, id=user_id)
    last_id = request.GET.get("last_id")

    query = Q(sender=other_user, receiver=request.user) | Q(
        sender=request.user, receiver=other_user
    )
    if last_id:
        messages = ChatMessage.objects.filter(query, id__gt=last_id).order_by(
            "timestamp"
        )
    else:
        messages = ChatMessage.objects.filter(query).order_by("timestamp")

    data = []
    for msg in messages:
        data.append(
            {
                "id": msg.id,
                "sender_id": msg.sender.id,
                "message": msg.message,
                "timestamp": msg.timestamp.strftime("%H:%M"),
                "is_me": msg.sender == request.user,
            }
        )

    return JsonResponse({"messages": data})


@login_required
def profile(request):
    """Profile view"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")
    return render(request, "user/profile.html")


@login_required
def profile_edit(request):
    """Profile edit view"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    profile = request.user.profile
    if request.method == "POST":
        request.user.first_name = request.POST.get(
            "first_name", request.user.first_name
        )
        request.user.last_name = request.POST.get("last_name", request.user.last_name)
        request.user.email = request.POST.get("email", request.user.email)
        request.user.save()

        profile.full_name = f"{request.user.first_name} {request.user.last_name}"
        profile.address = request.POST.get("address", profile.address)
        profile.income_source = request.POST.get("income_source", profile.income_source)

        income = request.POST.get("monthly_income")
        if income:
            try:
                profile.monthly_income = float(income)
            except ValueError:
                pass

        profile.save()
        messages.success(request, "Profile updated successfully!")
        return redirect("profile")

    return render(request, "user/profile_edit.html", {"profile": profile})


@login_required
def transactions(request):
    """Transactions view"""
    if request.user.is_superuser:
        return redirect("admin_dashboard")

    borrows = MoneyTransaction.objects.filter(borrower=request.user).order_by(
        "-created_at"
    )
    lends = MoneyTransaction.objects.filter(lender=request.user).order_by("-created_at")
    goods_borrows = GoodsTransaction.objects.filter(borrower=request.user).order_by(
        "-created_at"
    )
    goods_lends = GoodsTransaction.objects.filter(lender=request.user).order_by(
        "-created_at"
    )

    # Filter variables
    search_q = request.GET.get("search", "")
    status = request.GET.get("status", "")
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    min_interest = request.GET.get("min_interest", "")
    max_interest = request.GET.get("max_interest", "")

    if search_q:
        borrows = borrows.filter(
            Q(lender__username__icontains=search_q)
            | Q(lender__first_name__icontains=search_q)
            | Q(lender__last_name__icontains=search_q)
        )
        lends = lends.filter(
            Q(borrower__username__icontains=search_q)
            | Q(borrower__first_name__icontains=search_q)
            | Q(borrower__last_name__icontains=search_q)
        )
        goods_borrows = goods_borrows.filter(
            Q(item__item_name__icontains=search_q)
            | Q(lender__username__icontains=search_q)
            | Q(lender__first_name__icontains=search_q)
            | Q(lender__last_name__icontains=search_q)
        )
        goods_lends = goods_lends.filter(
            Q(item__item_name__icontains=search_q)
            | Q(borrower__username__icontains=search_q)
            | Q(borrower__first_name__icontains=search_q)
            | Q(borrower__last_name__icontains=search_q)
        )

    if status:
        borrows = borrows.filter(status=status)
        lends = lends.filter(status=status)
        goods_borrows = goods_borrows.filter(status=status)
        goods_lends = goods_lends.filter(status=status)

    if start_date:
        borrows = borrows.filter(created_at__date__gte=start_date)
        lends = lends.filter(created_at__date__gte=start_date)
        goods_borrows = goods_borrows.filter(created_at__date__gte=start_date)
        goods_lends = goods_lends.filter(created_at__date__gte=start_date)

    if end_date:
        borrows = borrows.filter(created_at__date__lte=end_date)
        lends = lends.filter(created_at__date__lte=end_date)
        goods_borrows = goods_borrows.filter(created_at__date__lte=end_date)
        goods_lends = goods_lends.filter(created_at__date__lte=end_date)

    if min_interest:
        try:
            borrows = borrows.filter(interest_rate__gte=Decimal(min_interest))
            lends = lends.filter(interest_rate__gte=Decimal(min_interest))
        except:
            pass

    if max_interest:
        try:
            borrows = borrows.filter(interest_rate__lte=Decimal(max_interest))
            lends = lends.filter(interest_rate__lte=Decimal(max_interest))
        except:
            pass

    if request.method == "POST":
        action = request.POST.get("action")
        tx_id = request.POST.get("transaction_id")
        tx = get_object_or_404(MoneyTransaction, id=tx_id)

        if action == "repay":
            # Redirect to eSewa repayment flow
            return redirect("esewa_repayment_initiate", transaction_id=tx.id)

    context = {
        "borrows": borrows,
        "lendings": lends,
        "goods_borrows": goods_borrows,
        "goods_lends": goods_lends,
        "filters": request.GET,
    }
    return render(request, "user/transactions.html", context)


# Removed duplicate reviews view


# Admin Views (require superuser)
@login_required
def admin_dashboard(request):
    """Admin dashboard view"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")

    today = timezone.now().date()

    context = {
        "total_users": User.objects.exclude(is_superuser=True).count(),
        "verified_users": UserProfile.objects.filter(kyc_status="APPROVED").count(),
        "pending_kyc": UserProfile.objects.filter(kyc_status="PENDING").count(),
        "new_users_today": User.objects.filter(date_joined__date=today)
        .exclude(is_superuser=True)
        .count(),
        "active_loans": MoneyTransaction.objects.filter(status="ACTIVE").count(),
        "total_volume": MoneyTransaction.objects.aggregate(total=Avg("amount"))["total"]
        or 0,  # Should be sum, fixing below
        "recent_transactions": MoneyTransaction.objects.all().order_by("-created_at")[
            :5
        ],
        "recent_users": User.objects.exclude(is_superuser=True).order_by(
            "-date_joined"
        )[:5],
    }

    # Correction: total_volume should be Sum
    from django.db.models import Sum

    context["total_volume"] = (
        MoneyTransaction.objects.aggregate(total=Sum("amount"))["total"] or 0
    )

    return render(request, "admin/dashboard.html", context)


@login_required
def admin_user_management(request):
    """Admin user management view"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")

    query = request.GET.get("q", "")
    if query:
        users = User.objects.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        ).exclude(is_superuser=True)
    else:
        users = User.objects.exclude(is_superuser=True)

    if request.method == "POST":
        action = request.POST.get("action")
        user_id = request.POST.get("user_id")
        target_user = get_object_or_404(User, id=user_id)

        if action == "delete":
            target_user.delete()
            messages.success(request, f"User {target_user.username} deleted.")
        elif action == "toggle_status":
            target_user.is_active = not target_user.is_active
            target_user.save()
            status = "activated" if target_user.is_active else "deactivated"
            messages.success(
                request, f"User {target_user.username} {status}.", extra_tags="admin"
            )

        return redirect("admin_user_management")

    return render(
        request, "admin/user_management.html", {"users": users, "query": query}
    )


@login_required
def admin_kyc_verification(request):
    """Admin KYC verification view"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")

    # Filter profiles that have been submitted and are pending review
    kyc_requests = UserProfile.objects.filter(kyc_status="PENDING").exclude(
        user__is_superuser=True
    )

    if request.method == "POST":
        profile_id = request.POST.get("profile_id")
        action = request.POST.get("action")
        profile = get_object_or_404(UserProfile, id=profile_id)

        if action == "approve":
            profile.kyc_status = "APPROVED"
            profile.kyc_verified = True
            profile.save()
            Notification.objects.create(
                user=profile.user,
                message="Your KYC has been approved! You can now start lending and borrowing.",
            )
            messages.success(
                request, f"Approved KYC for {profile.user.username}", extra_tags="admin"
            )
        elif action == "reject":
            profile.kyc_status = "REJECTED"
            profile.kyc_verified = False
            profile.save()
            Notification.objects.create(
                user=profile.user,
                message="Your KYC was rejected. Please resubmit with correct details.",
            )
            messages.error(
                request, f"Rejected KYC for {profile.user.username}", extra_tags="admin"
            )

        return redirect("admin_kyc_verification")

    return render(
        request, "admin/kyc_verification.html", {"kyc_requests": kyc_requests}
    )


@login_required
def admin_reports(request):
    """Admin reports view"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")

    from django.db.models import Avg, Sum

    # All time report
    all_time_stats = {
        "period": "All Time",
        "transaction_count": MoneyTransaction.objects.count(),
        "total_amount": MoneyTransaction.objects.aggregate(total=Sum("amount"))["total"]
        or 0,
        "avg_interest": MoneyTransaction.objects.aggregate(avg=Avg("interest_rate"))[
            "avg"
        ]
        or 0,
    }

    # Add more periods if needed, but template expects a list 'reports'
    reports = [all_time_stats]

    return render(request, "admin/reports.html", {"reports": reports})


@login_required
def admin_user_detail(request, user_id):
    """Admin detailed view of a specific user"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")

    target_user = get_object_or_404(User, id=user_id)
    profile = target_user.profile

    # Financial Stats for this user
    active_borrows = MoneyTransaction.objects.filter(
        borrower=target_user, status="ACTIVE"
    )
    active_lendings = MoneyTransaction.objects.filter(
        lender=target_user, status="ACTIVE"
    )

    borrows_amount = sum(tx.amount for tx in active_borrows)
    lendings_amount = sum(tx.amount for tx in active_lendings)

    # Recent Transactions for this user
    recent_transactions = MoneyTransaction.objects.filter(
        Q(lender=target_user) | Q(borrower=target_user)
    ).order_by("-created_at")[:10]

    context = {
        "target_user": target_user,
        "profile": profile,
        "borrows_amount": borrows_amount,
        "lendings_amount": lendings_amount,
        "recent_transactions": recent_transactions,
        "borrows_count": active_borrows.count(),
        "lendings_count": active_lendings.count(),
    }
    return render(request, "admin/user_detail.html", context)


@login_required
def initiate_password_change(request):
    """Initiate password change for logged in user via OTP"""
    user = request.user
    email = user.email

    # Generate 6-digit code
    code = "".join(random.choices(string.digits, k=6))
    PasswordResetCode.objects.create(user=user, code=code)

    # Send email
    subject = "Your LenDen Verification Code"
    message = f"Hello {user.username},\n\nYour verification code for security update is: {code}\n\nThis code will expire in 10 minutes."
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [email]

    try:
        send_mail(subject, message, from_email, recipient_list)
        request.session["reset_email"] = email
        messages.success(request, "Verification code sent to your registered email.")
        return redirect("verify_code")
    except Exception as e:
        messages.error(request, f"Error sending email: {str(e)}")
        return redirect("profile")


def forgot_password(request):
    """Generate and send verification code"""
    if request.method == "POST":
        email = request.POST.get("email")
        user = User.objects.filter(email=email).first()

        if user:
            # Generate 6-digit code
            code = "".join(random.choices(string.digits, k=6))
            PasswordResetCode.objects.create(user=user, code=code)

            # Send email
            subject = "Your LenDen Verification Code"
            message = f"Hello {user.username},\n\nYour verification code for password reset is: {code}\n\nThis code will expire in 10 minutes."
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [email]

            try:
                send_mail(subject, message, from_email, recipient_list)
                request.session["reset_email"] = email
                messages.success(request, "Verification code sent to your email.")
                return redirect("verify_code")
            except Exception as e:
                messages.error(request, f"Error sending email: {str(e)}")
        else:
            messages.error(request, "No user found with this email address.")

    return render(request, "auth/forgot_password.html", {"hide_nav": True})


def verify_code(request):
    """Verify the 6-digit code for password reset"""
    email = request.session.get("reset_email")
    if not email:
        return redirect("forgot_password")

    if request.method == "POST":
        code = request.POST.get("code")
        user = User.objects.filter(email=email).first()

        if user:
            reset_code = (
                PasswordResetCode.objects.filter(user=user, code=code)
                .order_by("-created_at")
                .first()
            )
            if reset_code and reset_code.is_valid():
                request.session["code_verified"] = True
                return redirect("reset_password")
            else:
                messages.error(request, "Invalid or expired verification code.")
        else:
            return redirect("forgot_password")

    return render(
        request,
        "auth/verify_code.html",
        {"hide_nav": True, "email": email, "title": "Reset Password"},
    )


def reset_password(request):
    """Set new password"""
    email = request.session.get("reset_email")
    verified = request.session.get("code_verified")

    if not email or not verified:
        return redirect("forgot_password")

    if request.method == "POST":
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if password == confirm_password:
            user = User.objects.filter(email=email).first()
            if user:
                user.set_password(password)
                user.save()
                # Clear session
                if "reset_email" in request.session:
                    del request.session["reset_email"]
                if "code_verified" in request.session:
                    del request.session["code_verified"]
                messages.success(
                    request, "Password reset successful! You can now login."
                )
                return redirect("login")
            else:
                return redirect("forgot_password")
        else:
            messages.error(request, "Passwords do not match.")

    return render(request, "auth/reset_password.html", {"hide_nav": True})


@login_required
def esewa_initiate(request, transaction_id):
    """Initiate eSewa payment for a lending transaction"""
    transaction = get_object_or_404(
        MoneyTransaction, id=transaction_id, lender=request.user
    )

    if transaction.status != "PENDING":
        messages.error(request, "This transaction is not in a payable state.")
        return redirect("transactions")

    esewa = EsewaService()
    success_url = request.build_absolute_uri(reverse("esewa_callback"))
    failure_url = request.build_absolute_uri(reverse("transactions"))

    # eSewa V2 uses a form POST redirection.
    # Since we need to redirect the user to eSewa with a POST,
    # we'll render a auto-submitting form template.

    import uuid

    unique_uuid = f"{transaction.id}-{uuid.uuid4().hex[:8]}"

    payload = esewa.get_payment_payload(
        amount=transaction.amount,
        transaction_uuid=unique_uuid,
        success_url=success_url,
        failure_url=failure_url,
    )

    transaction.payment_status = "INITIATED"
    transaction.save()

    return render(
        request,
        "user/esewa_redirect.html",
        {"payload": payload, "esewa_url": esewa.base_url},
    )


@login_required
def esewa_repayment_initiate(request, transaction_id):
    """Initiate eSewa payment for a repayment"""
    transaction = get_object_or_404(
        MoneyTransaction, id=transaction_id, borrower=request.user
    )

    if transaction.status != "ACTIVE":
        messages.error(request, "This transaction is not in an active state.")
        return redirect("transactions")

    # Calculate final amount including interest and fines
    total_repayment = transaction.calculate_interest()
    today = datetime.date.today()
    if today > transaction.deadline:
        fine_amount = total_repayment * Decimal("0.05")
        total_repayment += fine_amount

    esewa = EsewaService()
    success_url = request.build_absolute_uri(reverse("esewa_callback"))
    failure_url = request.build_absolute_uri(reverse("transactions"))

    import uuid

    unique_uuid = f"{transaction.id}-{uuid.uuid4().hex[:8]}"

    payload = esewa.get_payment_payload(
        amount=total_repayment,
        transaction_uuid=unique_uuid,
        success_url=success_url,
        failure_url=failure_url,
    )

    transaction.payment_status = "REPAYMENT_INITIATED"
    transaction.save()

    return render(
        request,
        "user/esewa_redirect.html",
        {"payload": payload, "esewa_url": esewa.base_url},
    )


@login_required
def esewa_callback(request):
    """Handle return from eSewa after payment attempt"""
    encoded_data = request.GET.get("data")

    if not encoded_data:
        messages.error(request, "Invalid payment callback.")
        return redirect("transactions")

    try:
        decoded_data = base64.b64decode(encoded_data).decode("utf-8")
        data = json.loads(decoded_data)
    except Exception as e:
        logger.error(f"eSewa Callback Decode Error: {str(e)}")
        messages.error(request, "Failed to process eSewa response.")
        return redirect("transactions")

    transaction_uuid = data.get("transaction_uuid")
    # Extract original transaction ID from unique UUID (formatted as ID-SUFFIX)
    transaction_id = transaction_uuid.split("-")[0]
    transaction = get_object_or_404(MoneyTransaction, id=transaction_id)

    if data.get("status") == "COMPLETE":
        if transaction.status == "PENDING":
            # FUNDING FLOW
            transaction.payment_status = "COMPLETED"
            transaction.status = "ACTIVE"
            transaction.khalti_transaction_id = data.get("transaction_code")
            transaction.save()

            if transaction.loan_offer:
                transaction.loan_offer.is_active = False
                transaction.loan_offer.save()

            Notification.objects.create(
                user=transaction.borrower,
                message=f"{transaction.lender.username} has funded your loan request of Rs. {transaction.amount} via eSewa!",
            )
            messages.success(
                request,
                f"Payment successful! Loan to {transaction.borrower.username} is now active.",
            )

        elif transaction.status == "ACTIVE":
            # REPAYMENT FLOW
            transaction.payment_status = "REPAID"
            transaction.status = "REPAID"
            transaction.save()

            # Post-repayment logic (Trust score update etc)
            transaction.borrower.profile.update_trust_score()

            Notification.objects.create(
                user=transaction.lender,
                message=f"{transaction.borrower.username} has repaid the amount of Rs. {transaction.amount} via eSewa!",
            )
            messages.success(
                request,
                f"Repayment successful! Loan from {transaction.lender.username} is now repaid.",
            )
    else:
        transaction.payment_status = "FAILED"
        transaction.save()
        messages.error(
            request, f"Payment failed or was cancelled. Status: {data.get('status')}"
        )

    return redirect("transactions")


@login_required
def view_public_profile(request, user_id):
    """View another user's public profile"""
    target_user = get_object_or_404(User, id=user_id)
    profile = target_user.profile

    # Don't allow viewing own public profile through this view (redirect to own profile)
    if target_user == request.user:
        return redirect("profile")

    # Get user's active offers
    loan_offers = LoanOffer.objects.filter(lender=target_user, is_active=True)
    goods_offered = GoodsExchange.objects.filter(owner=target_user, available=True)

    # Get reviews received by this user
    reviews = Review.objects.filter(reviewee=target_user).order_by("-created_at")

    # Statistics
    stats = {
        "successful_loans": MoneyTransaction.objects.filter(
            lender=target_user, status="REPAID"
        ).count(),
        "active_loans": MoneyTransaction.objects.filter(
            lender=target_user, status="ACTIVE"
        ).count(),
        "trust_score": profile.trust_score,
        "rating": profile.rating,
    }

    context = {
        "target_user": target_user,
        "profile": profile,
        "loan_offers": loan_offers,
        "goods_offered": goods_offered,
        "reviews": reviews,
        "stats": stats,
    }
    return render(request, "user/public_profile.html", context)
