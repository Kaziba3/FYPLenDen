from django.urls import path
from . import views
from django.contrib.auth import views as auth_views


urlpatterns = [
    # Home page
    path('', views.home, name='home'),
    
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    
    # KYC URLs
    path('kyc/', views.kyc_form, name='kyc_form'),
    path('kyc/submit/', views.kyc_submit, name='kyc_submit'),
    
    # User Dashboard URLs
    path('dashboard/', views.user_dashboard, name='user_dashboard'),
    path('marketplace/', views.marketplace, name='marketplace'),
    path('borrow/', views.borrow, name='borrow'),
    path('lend/', views.lend, name='lend'),
    path('exchange/', views.exchange, name='exchange'),
    path('friends/', views.friends, name='friends'),
    path('chat/', views.chat, name='chat'),
    path('profile/', views.profile, name='profile'),
    path('transactions/', views.transactions, name='transactions'),
    path('reviews/', views.reviews, name='reviews'),
    
    # Admin URLs (only accessible by admin users)
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/users/', views.admin_user_management, name='admin_user_management'),
    path('admin/kyc/', views.admin_kyc_verification, name='admin_kyc_verification'),
    path('admin/reports/', views.admin_reports, name='admin_reports'),
    
    path('forgot-password/', views.forgot_password, name='forgot_password'),

     # Or use Django's built-in password reset URLs (recommended)
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='auth/password_reset.html',
        email_template_name='auth/password_reset_email.html',
        subject_template_name='auth/password_reset_subject.txt'
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='auth/password_reset_done.html'
    ), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='auth/password_reset_confirm.html'
    ), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='auth/password_reset_complete.html'
    ), name='password_reset_complete'),
]