from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponseForbidden

def home(request):
    """Home page view"""
    # If user is authenticated, redirect to dashboard
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('admin_dashboard')
        else:
            return redirect('user_dashboard')
    
    # Show landing page for unauthenticated users
    return render(request, 'landing.html', {'hide_nav': True})

def login_view(request):
    """Login view"""
    if request.user.is_authenticated:
        return redirect('user_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            auth_login(request, user)
            if user.is_superuser:
                return redirect('admin_dashboard')
            else:
                return redirect('user_dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'auth/login.html', {'hide_nav': True})

def signup_view(request):
    """Signup view"""
    if request.user.is_authenticated:
        return redirect('user_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            auth_login(request, user)
            messages.success(request, 'Account created successfully! Please complete KYC verification.')
            return redirect('kyc_form')
        except Exception as e:
            messages.error(request, f'Error creating account: {str(e)}')
    
    return render(request, 'auth/signup.html', {'hide_nav': True})

def logout_view(request):
    """Logout view"""
    auth_logout(request)
    return redirect('home')

@login_required
def kyc_form(request):
    """KYC form view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'auth/kyc_form.html')

@login_required
def kyc_submit(request):
    """Handle KYC submission"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    
    if request.method == 'POST':
        # Process KYC data here
        messages.success(request, 'KYC submitted successfully! It will be reviewed within 24 hours.')
        return redirect('user_dashboard')
    
    return redirect('kyc_form')

# User Views
@login_required
def user_dashboard(request):
    """User dashboard view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    
    # Get user's borrowing limit based on income and age
    # This is a placeholder - implement your actual logic
    can_borrow = 50000  # Example amount
    
    context = {
        'can_borrow': can_borrow,
    }
    return render(request, 'user/dashboard.html', context)

@login_required
def marketplace(request):
    """Marketplace view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'user/marketplace.html')

@login_required
def borrow(request):
    """Borrow view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'user/borrow.html')

@login_required
def lend(request):
    """Lend view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'user/lend.html')

@login_required
def exchange(request):
    """Exchange view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'user/exchange.html')

@login_required
def friends(request):
    """Friends view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'user/friends.html')

@login_required
def chat(request):
    """Chat view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'user/chat.html')

@login_required
def profile(request):
    """Profile view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'user/profile.html')

@login_required
def transactions(request):
    """Transactions view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'user/transactions.html')

@login_required
def reviews(request):
    """Reviews view"""
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    return render(request, 'user/reviews.html')

# Admin Views (require superuser)
@login_required
def admin_dashboard(request):
    """Admin dashboard view"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")
    return render(request, 'admin/dashboard.html')

@login_required
def admin_user_management(request):
    """Admin user management view"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")
    return render(request, 'admin/user_management.html')

@login_required
def admin_kyc_verification(request):
    """Admin KYC verification view"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")
    return render(request, 'admin/kyc_verification.html')

@login_required
def admin_reports(request):
    """Admin reports view"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")
    return render(request, 'admin/reports.html')

def forgot_password(request):
    """Simple forgot password page"""
    return render(request, 'auth/forgot_password.html', {'hide_nav': True})