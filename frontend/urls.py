from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    # Landing page
    path("", views.landing_page, name="landing_page"),
    # Authentication URLs
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("signup-verify-otp/", views.signup_verify_otp, name="signup_verify_otp"),
    path("logout/", views.logout_view, name="logout"),
    # KYC URLs
    path("kyc/", views.kyc_form, name="kyc_form"),
    path("kyc/submit/", views.kyc_submit, name="kyc_submit"),
    # User Dashboard URLs
    path("dashboard/", views.user_dashboard, name="user_dashboard"),
    path("marketplace/", views.marketplace, name="marketplace"),
    path("borrow/", views.borrow, name="borrow"),
    path("borrow/<int:offer_id>/", views.borrow, name="borrow_offer"),
    path("lend/", views.lend, name="lend"),
    path("goods/", views.goods, name="goods"),
    path("friends/", views.friends, name="friends"),
    path("chat/", views.chat, name="chat"),
    path("chat/get_messages/<int:user_id>/", views.get_messages, name="get_messages"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    path(
        "profile/<int:user_id>/", views.view_public_profile, name="view_public_profile"
    ),
    path("transactions/", views.transactions, name="transactions"),
    path("reviews/", views.reviews, name="reviews"),
    path("reviews/submit/", views.submit_review, name="submit_review"),
    # Goods Exchange Transaction URLs
    path(
        "goods/request/<int:item_id>/", views.request_exchange, name="request_exchange"
    ),
    path(
        "goods/manage/<int:transaction_id>/",
        views.manage_exchange,
        name="manage_exchange",
    ),
    path(
        "goods/complete/<int:transaction_id>/",
        views.complete_exchange,
        name="complete_exchange",
    ),
    path("goods/my-exchanges/", views.my_exchanges, name="my_exchanges"),
    # Admin URLs (only accessible by admin users)
    path("panel/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("panel/users/", views.admin_user_management, name="admin_user_management"),
    path("panel/kyc/", views.admin_kyc_verification, name="admin_kyc_verification"),
    path("panel/reports/", views.admin_reports, name="admin_reports"),
    path("panel/users/<int:user_id>/", views.admin_user_detail, name="view_user"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path(
        "initiate-password-change/",
        views.initiate_password_change,
        name="initiate_password_change",
    ),
    path("verify-code/", views.verify_code, name="verify_code"),
    path("reset-password/", views.reset_password, name="reset_password"),
    # Or use Django's built-in password reset URLs (recommended)
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="auth/password_reset.html",
            email_template_name="auth/password_reset_email.html",
            subject_template_name="auth/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="auth/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="auth/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="auth/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    # eSewa Payment URLs
    path(
        "esewa/initiate/<int:transaction_id>/",
        views.esewa_initiate,
        name="esewa_initiate",
    ),
    path(
        "esewa/repay/<int:transaction_id>/",
        views.esewa_repayment_initiate,
        name="esewa_repayment_initiate",
    ),
    path("esewa/callback/", views.esewa_callback, name="esewa_callback"),
]
