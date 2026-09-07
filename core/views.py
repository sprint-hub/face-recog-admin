from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from django.http import HttpResponse, JsonResponse
import csv
import json
import logging
import uuid
import hashlib
from .models import (Client, ClientWallet, Transaction, Verification, BVNVerification, AuditLog, User)
from .forms import (ClientForm, FundClientForm, VerificationReportForm, LoginForm, ClientEditForm, UserProfileForm)


logger = logging.getLogger(__name__)


# ============ AUTHENTICATION VIEWS ============

class CustomLoginView(LoginView):
    """Custom login view that handles email-based authentication"""
    form_class = LoginForm
    template_name = 'admin/login.html'
    redirect_authenticated_user = True
    success_url = reverse_lazy('core:dashboard')
    
    def post(self, request, *args, **kwargs):
        print("="*60)
        print("LOGIN ATTEMPT")
        print("="*60)
        print(f"Email: {request.POST.get('username')}")
        print(f"Password: {'*' * len(request.POST.get('password', ''))}")
        print("="*60)
        
        return super().post(request, *args, **kwargs)
    
    def form_valid(self, form):
        """Handle successful login"""
        user = form.get_user()
        
        print("="*60)
        print("LOGIN SUCCESSFUL")
        print(f"User: {user.email}")
        print("="*60)
        
        try:
            AuditLog.objects.create(
                user=user,
                action='login',
                model_name='User',
                record_id=str(user.id),
                changes={
                    'login': 'successful',
                    'ip': self.request.META.get('REMOTE_ADDR', '')
                }
            )
        except Exception:
            pass
        
        messages.success(
            self.request, 
            f'Welcome back, {user.get_full_name() or user.email}!'
        )
        
        return super().form_valid(form)
    
    def form_invalid(self, form):
        """Handle failed login"""
        print("="*60)
        print("LOGIN FAILED")
        print(f"Form Errors: {form.errors}")
        print("="*60)
        
        messages.error(
            self.request, 
            'Invalid email or password. Please try again.'
        )
        
        return super().form_invalid(form)


def custom_logout(request):
    """Custom logout view"""
    if request.user.is_authenticated:
        try:
            AuditLog.objects.create(
                user=request.user,
                action='logout',
                model_name='User',
                record_id=str(request.user.id),
                changes={'logout': 'successful'}
            )
        except Exception:
            pass
    
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('core:login')


# ============ DASHBOARD ============

@staff_member_required
def dashboard(request):
    """Admin dashboard with statistics"""
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)
    
    # Statistics
    total_clients = Client.objects.count()
    active_clients = Client.objects.filter(status='active').count()
    total_verifications = Verification.objects.count()
    pending_verifications = Verification.objects.filter(status='pending').count()
    successful_verifications = Verification.objects.filter(status='success').count()
    failed_verifications = Verification.objects.filter(status='failed').count()
    
    # Revenue statistics
    total_revenue = Transaction.objects.filter(
        transaction_type='verification_fee',
        status='completed'
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    # Recent transactions
    recent_transactions = Transaction.objects.select_related(
        'client', 'created_by'
    ).order_by('-created_at')[:10]
    
    # Recent verifications
    recent_verifications = Verification.objects.select_related(
        'client', 'user'
    ).order_by('-started_at')[:10]
    
    # Daily verifications for the last 7 days
    daily_verifications = []
    for i in range(7, 0, -1):
        day = end_date - timedelta(days=i)
        count = Verification.objects.filter(
            started_at__date=day.date()
        ).count()
        daily_verifications.append({
            'date': day.strftime('%a'),
            'count': count
        })
    
    context = {
        'total_clients': total_clients,
        'active_clients': active_clients,
        'total_verifications': total_verifications,
        'pending_verifications': pending_verifications,
        'successful_verifications': successful_verifications,
        'failed_verifications': failed_verifications,
        'total_revenue': total_revenue,
        'recent_transactions': recent_transactions,
        'recent_verifications': recent_verifications,
        'daily_verifications': daily_verifications,
    }
    
    return render(request, 'admin/dashboard.html', context)


# ============ CLIENT MANAGEMENT ============

@staff_member_required
def clients_list(request):
    """List all clients with search and filters"""
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    tier_filter = request.GET.get('tier', '')
    
    clients = Client.objects.select_related('user', 'wallet').all()
    
    if query:
        clients = clients.filter(
            Q(company_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query)
        )
    
    if status_filter:
        clients = clients.filter(status=status_filter)
    
    if tier_filter:
        clients = clients.filter(tier=tier_filter)
    
    paginator = Paginator(clients, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
        'tier_filter': tier_filter,
    }
    
    return render(request, 'admin/clients/list.html', context)


@staff_member_required
def client_detail(request, pk):
    """View client details"""
    client = get_object_or_404(
        Client.objects.select_related('user', 'wallet'), 
        pk=pk
    )
    
    # Get recent transactions and verifications
    transactions = client.transactions.all().order_by('-created_at')[:50]
    verifications = client.verifications.all().order_by('-started_at')[:50]
    
    # Calculate stats
    total_verifications = client.verifications.count()
    successful = client.verifications.filter(status='success').count()
    failed = client.verifications.filter(status='failed').count()
    pending = client.verifications.filter(status='pending').count()
    
    context = {
        'client': client,
        'transactions': transactions,
        'verifications': verifications,
        'total_verifications': total_verifications,
        'successful': successful,
        'failed': failed,
        'pending': pending,
        'recent_transactions': transactions[:10],  # For the detail template
    }
    
    return render(request, 'admin/clients/detail.html', context)


@staff_member_required
def create_client(request):
    """Create new client"""
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            try:
                # Create user
                user = User.objects.create_user(
                    email=form.cleaned_data['email'],
                    username=form.cleaned_data['email'],
                    password=form.cleaned_data['password'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    is_client=True
                )
                
                # Create client
                client = Client.objects.create(
                    user=user,
                    company_name=form.cleaned_data['company_name'],
                    tier=form.cleaned_data['tier'],
                    monthly_verification_limit=form.cleaned_data['monthly_verification_limit'],
                    webhook_url=form.cleaned_data.get('webhook_url')
                )
                
                # Create wallet
                ClientWallet.objects.create(client=client)
                
                # Log action
                AuditLog.objects.create(
                    user=request.user,
                    client=client,
                    action='create',
                    model_name='Client',
                    record_id=client.id,
                    changes={'company_name': client.company_name}
                )
                
                messages.success(
                    request, 
                    f'Client {client.company_name} created successfully!'
                )
                
                # Show API credentials
                api_key = client.api_key
                api_secret = client.get_raw_api_secret()
                
                messages.info(request, f'API Key: {api_key}')
                if api_secret:
                    messages.info(
                        request, 
                        f'API Secret: {api_secret} (Save this now - it won\'t be shown again)'
                    )
                
                return redirect('core:client_detail', pk=client.id)
                
            except Exception as e:
                messages.error(request, f'Error creating client: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ClientForm()
    
    return render(request, 'admin/clients/create.html', {'form': form})


@staff_member_required
def edit_client(request, pk):
    """Edit existing client"""
    client = get_object_or_404(Client, pk=pk)
    
    if request.method == 'POST':
        form = ClientEditForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            
            AuditLog.objects.create(
                user=request.user,
                client=client,
                action='update',
                model_name='Client',
                record_id=client.id,
                changes={'updated': 'Client details updated'}
            )
            
            messages.success(
                request, 
                f'Client {client.company_name} updated successfully!'
            )
            return redirect('core:client_detail', pk=client.id)
    else:
        form = ClientEditForm(instance=client)
    
    return render(request, 'admin/clients/edit.html', {'form': form, 'client': client})


@staff_member_required
def delete_client(request, pk):
    """Delete/suspend a client"""
    client = get_object_or_404(Client, pk=pk)
    
    if request.method == 'POST':
        client.status = 'suspended'
        client.save()
        
        AuditLog.objects.create(
            user=request.user,
            client=client,
            action='delete',
            model_name='Client',
            record_id=client.id,
            changes={'status': 'suspended'}
        )
        
        messages.success(request, f'Client {client.company_name} has been suspended.')
        return redirect('core:clients_list')
    
    return render(request, 'admin/clients/delete.html', {'client': client})


@staff_member_required
def fund_client(request, pk):
    """Fund client wallet"""
    client = get_object_or_404(
        Client.objects.select_related('wallet'), 
        pk=pk
    )
    
    if request.method == 'POST':
        form = FundClientForm(request.POST)
        if form.is_valid():
            try:
                amount = form.cleaned_data['amount']
                notes = form.cleaned_data.get('notes', '')  # Changed from 'description' to 'notes'
                payment_method = form.cleaned_data.get('payment_method', 'manual')
                reference_id = form.cleaned_data.get('reference_id', '')
                
                wallet = client.wallet
                balance_before = wallet.current_balance
                wallet.update_balance(amount, is_credit=True)
                
                transaction = Transaction.objects.create(
                    client=client,
                    transaction_type='funding',
                    amount=amount,
                    is_credit=True,
                    balance_before=balance_before,
                    balance_after=wallet.current_balance,
                    description=notes,  # Store notes in description field
                    status='completed',
                    payment_method=payment_method,
                    reference_id=reference_id,
                    created_by=request.user
                )
                
                AuditLog.objects.create(
                    user=request.user,
                    client=client,
                    action='fund',
                    model_name='ClientWallet',
                    record_id=wallet.id,
                    changes={
                        'amount': str(amount), 
                        'new_balance': str(wallet.current_balance)
                    }
                )
                
                messages.success(
                    request, 
                    f'Successfully funded {client.company_name} with ${amount:.2f}'
                )
                return redirect('core:client_detail', pk=client.id)
                
            except Exception as e:
                messages.error(request, f'Error funding client: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = FundClientForm()
    
    # Get recent transactions for the sidebar
    recent_transactions = client.transactions.all().order_by('-created_at')[:5]
    
    return render(request, 'admin/clients/fund.html', {
        'form': form, 
        'client': client,
        'recent_transactions': recent_transactions
    })

@staff_member_required
def update_client_status(request, pk):
    """Update client status via AJAX or POST"""
    if request.method == 'POST':
        client = get_object_or_404(Client, pk=pk)
        new_status = request.POST.get('status')
        
        if new_status in dict(Client.STATUS_CHOICES):
            old_status = client.status
            client.status = new_status
            client.save()
            
            AuditLog.objects.create(
                user=request.user,
                client=client,
                action='status_change',
                model_name='Client',
                record_id=client.id,
                changes={
                    'old_status': old_status,
                    'new_status': new_status
                }
            )
            
            messages.success(
                request, 
                f'Client status updated to {client.get_status_display()}'
            )
            
            # If AJAX request, return JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'status': client.status,
                    'status_display': client.get_status_display()
                })
        else:
            messages.error(request, 'Invalid status selected.')
    
    return redirect('core:client_detail', pk=pk)


@staff_member_required
def regenerate_keys(request, pk):
    """Regenerate API keys for a client"""
    if request.method == 'POST':
        client = get_object_or_404(Client, pk=pk)
        
        try:
            # Generate new API key and secret
            import secrets
            import string
            
            # Generate random API key (32 chars)
            api_key = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
            api_key = f'pk_{api_key}'
            
            # Generate random API secret (64 chars)
            api_secret = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
            api_secret = f'sk_{api_secret}'
            
            # Save new keys
            client.api_key = api_key
            client.set_api_secret(api_secret)  # Assuming you have this method
            client.save()
            
            AuditLog.objects.create(
                user=request.user,
                client=client,
                action='regenerate_keys',
                model_name='Client',
                record_id=client.id,
                changes={'action': 'API keys regenerated'}
            )
            
            messages.success(request, 'API keys regenerated successfully!')
            
            # Show new keys
            messages.info(request, f'New API Key: {api_key}')
            messages.info(
                request, 
                f'New API Secret: {api_secret} (Save this now - it won\'t be shown again)'
            )
            
            # If AJAX request, return JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'api_key': api_key,
                    'api_secret': api_secret
                })
                
        except Exception as e:
            messages.error(request, f'Error regenerating keys: {str(e)}')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=400)
    
    return redirect('core:client_detail', pk=pk)


# ============ VERIFICATION MANAGEMENT ============

@staff_member_required
def verifications_list(request):
    """List all verifications with filters"""
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    verifications = Verification.objects.select_related('client', 'user').all()
    
    if query:
        verifications = verifications.filter(
            Q(id__icontains=query) |
            Q(client__company_name__icontains=query) |
            Q(user__email__icontains=query)
        )
    
    if status_filter:
        verifications = verifications.filter(status=status_filter)
    
    if type_filter:
        verifications = verifications.filter(verification_type=type_filter)
    
    if date_from:
        verifications = verifications.filter(started_at__date__gte=date_from)
    
    if date_to:
        verifications = verifications.filter(started_at__date__lte=date_to)
    
    paginator = Paginator(verifications, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'admin/verifications/list.html', context)


@staff_member_required
def verification_detail(request, pk):
    """View verification details"""
    verification = get_object_or_404(
        Verification.objects.select_related('client', 'user', 'bvn_verification'),
        pk=pk
    )
    
    return render(request, 'admin/verifications/detail.html', {'verification': verification})


@staff_member_required
def verification_export_csv(request):
    """Export verifications to CSV"""
    verifications = Verification.objects.select_related('client', 'user').all()
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="verifications_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Client', 'User', 'Type', 'Status', 
        'Face Score', 'Liveness Score', 'Cost', 
        'Started At', 'Completed At'
    ])
    
    for v in verifications:
        writer.writerow([
            v.id[:8],
            v.client.company_name,
            v.user.email if v.user else 'N/A',
            v.get_verification_type_display(),
            v.get_status_display(),
            v.face_match_score or 'N/A',
            v.liveness_score or 'N/A',
            str(v.cost),
            v.started_at.strftime('%Y-%m-%d %H:%M'),
            v.completed_at.strftime('%Y-%m-%d %H:%M') if v.completed_at else 'N/A'
        ])
    
    return response


# ============ REPORTS ============

@staff_member_required
def generate_report(request):
    """Generate verification report"""
    if request.method == 'POST':
        form = VerificationReportForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            client = form.cleaned_data.get('client')
            status = form.cleaned_data.get('status')
            export_format = form.cleaned_data.get('format', 'html')
            
            verifications = Verification.objects.filter(
                started_at__date__gte=start_date,
                started_at__date__lte=end_date
            )
            
            if client:
                verifications = verifications.filter(client=client)
            
            if status:
                verifications = verifications.filter(status=status)
            
            total = verifications.count()
            successful = verifications.filter(status='success').count()
            failed = verifications.filter(status='failed').count()
            pending = verifications.filter(status='pending').count()
            
            revenue = verifications.filter(status='success').aggregate(
                total_revenue=Sum('cost')
            )['total_revenue'] or Decimal('0.00')
            
            # Export CSV
            if export_format == 'csv':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = (
                    f'attachment; filename="verification_report_{start_date}_{end_date}.csv"'
                )
                
                writer = csv.writer(response)
                writer.writerow([
                    'ID', 'Client', 'Status', 'Type', 'Face Score', 'Liveness Score',
                    'Cost', 'Started At', 'Completed At'
                ])
                
                for v in verifications:
                    writer.writerow([
                        v.id[:8],
                        v.client.company_name,
                        v.get_status_display(),
                        v.get_verification_type_display(),
                        v.face_match_score or 'N/A',
                        v.liveness_score or 'N/A',
                        str(v.cost),
                        v.started_at.strftime('%Y-%m-%d %H:%M'),
                        v.completed_at.strftime('%Y-%m-%d %H:%M') if v.completed_at else 'N/A'
                    ])
                
                return response
            
            context = {
                'verifications': verifications,
                'total': total,
                'successful': successful,
                'failed': failed,
                'pending': pending,
                'revenue': revenue,
                'start_date': start_date,
                'end_date': end_date,
                'client': client,
            }
            
            return render(request, 'admin/reports/verification.html', context)
    else:
        form = VerificationReportForm()
    
    return render(request, 'admin/reports/form.html', {'form': form})


# ============ API / AJAX ENDPOINTS ============

@staff_member_required
def get_client_stats(request):
    """Get client statistics for dashboard widgets (AJAX)"""
    client_id = request.GET.get('client_id')
    if client_id:
        client = get_object_or_404(Client, pk=client_id)
        data = {
            'name': client.company_name,
            'balance': str(client.balance),
            'total_verifications': client.verifications.count(),
            'successful': client.verifications.filter(status='success').count(),
            'failed': client.verifications.filter(status='failed').count(),
        }
        return JsonResponse(data)
    return JsonResponse({'error': 'Client ID required'}, status=400)


@staff_member_required
def recent_activity(request):
    """Get recent activity for dashboard (AJAX)"""
    transactions = Transaction.objects.select_related('client').order_by('-created_at')[:10]
    verifications = Verification.objects.select_related('client').order_by('-started_at')[:10]
    
    data = {
        'transactions': [
            {
                'reference': t.reference,
                'client': t.client.company_name,
                'amount': str(t.amount),
                'status': t.status,
                'date': t.created_at.strftime('%Y-%m-%d %H:%M')
            }
            for t in transactions
        ],
        'verifications': [
            {
                'id': v.id[:8],
                'client': v.client.company_name,
                'status': v.status,
                'date': v.started_at.strftime('%Y-%m-%d %H:%M')
            }
            for v in verifications
        ]
    }
    return JsonResponse(data)


@csrf_exempt
@require_GET
def validate_api_key(request):
    """
    Validate API key for FastAPI
    
    Headers:
        X-API-Key: Client's API key
        X-Internal-Secret: Internal secret for service-to-service auth
    
    Returns:
        JSON with client data if valid
    """
    
    # Verify internal secret
    internal_secret = request.headers.get('X-Internal-Secret')
    if internal_secret != getattr(settings, 'INTERNAL_API_SECRET', None):
        logger.warning("Invalid internal secret for API key validation")
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    # Get API key from header
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return JsonResponse({'error': 'API key required'}, status=400)
    
    try:
        # Find client by API key
        client = Client.objects.select_related('wallet').get(api_key=api_key)
        
        # Check if client is active
        if client.status != 'active':
            return JsonResponse({
                'valid': False,
                'status': client.status,
                'message': f'Client account is {client.status}'
            }, status=403)
        
        # Get wallet balance
        balance = client.wallet.current_balance if hasattr(client, 'wallet') else Decimal('0.00')
        
        # Count verifications this month
        current_month = timezone.now().month
        current_year = timezone.now().year
        verifications_this_month = client.verifications.filter(
            started_at__month=current_month,
            started_at__year=current_year
        ).count()
        
        # Prepare response
        response_data = {
            'valid': True,
            'id': str(client.id),
            'company_name': client.company_name,
            'status': client.status,
            'tier': client.tier,
            'balance': float(balance),
            'monthly_verification_limit': client.monthly_verification_limit,
            'verifications_this_month': verifications_this_month,
            'total_spent': float(client.total_spent or Decimal('0.00')),
            'created_at': client.created_at.isoformat()
        }
        
        return JsonResponse(response_data)
        
    except Client.DoesNotExist:
        return JsonResponse({
            'valid': False,
            'message': 'Invalid API key'
        }, status=401)
        
    except Exception as e:
        logger.error(f"API key validation error: {str(e)}")
        return JsonResponse({
            'valid': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_POST
def track_verification_usage(request):
    """
    Track verification usage for client (called by FastAPI)
    """
    
    # Verify internal secret
    internal_secret = request.headers.get('X-Internal-Secret')
    if internal_secret != getattr(settings, 'INTERNAL_API_SECRET', None):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        data = json.loads(request.body)
        api_key = data.get('api_key')
        
        if not api_key:
            return JsonResponse({'error': 'API key required'}, status=400)
        
        # Find client
        client = Client.objects.get(api_key=api_key)
        
        # Update usage statistics ONLY
        client.verifications_this_month += 1
        client.save(update_fields=['verifications_this_month'])
        
        return JsonResponse({
            'status': 'success',
            'client_id': str(client.id),
            'verifications_this_month': client.verifications_this_month,
            'remaining_limit': client.monthly_verification_limit - client.verifications_this_month
        })
        
    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Usage tracking error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def verification_webhook(request):
    """
    Receive verification data from FastAPI
    This is the SINGLE source of truth for billing.
    """
    
    # Verify webhook secret
    webhook_secret = request.headers.get('X-Webhook-Secret')
    if webhook_secret != getattr(settings, 'WEBHOOK_SECRET', None):
        logger.warning(f"Invalid webhook secret")
        return JsonResponse({'error': 'Invalid webhook secret'}, status=403)
    
    try:
        data = json.loads(request.body)
        logger.info(f"Webhook received: {data.get('verification_id')}")
        
        # Find client
        client = None
        client_id = data.get('client_id')
        api_key = data.get('api_key')
        
        if client_id:
            try:
                client = Client.objects.get(id=client_id)
                logger.info(f"Found client by ID: {client.company_name}")
            except Client.DoesNotExist:
                pass
        
        if not client and api_key:
            try:
                client = Client.objects.get(api_key=api_key)
                logger.info(f"Found client by API key: {client.company_name}")
            except Client.DoesNotExist:
                pass
        
        if not client:
            logger.error(f"Client not found - ID: {client_id}, API Key: {api_key[:10] if api_key else 'None'}...")
            return JsonResponse({'error': 'Client not found'}, status=404)
        
        with transaction.atomic():
            
            # Create or update BVN verification
            bvn = data.get('bvn')
            bvn_verification = None
            
            if bvn:
                bvn_verification = BVNVerification.objects.filter(bvn=bvn).first()
                
                if not bvn_verification:
                    bvn_verification = BVNVerification.objects.create(
                        client=client,
                        bvn=bvn,
                        hash_bvn=hashlib.sha256(bvn.encode()).hexdigest(),
                        status='success' if data.get('matched') else 'failed',
                        verified_at=timezone.now()
                    )
            
            # Create Verification record
            verification = Verification.objects.create(
                client=client,
                bvn_verification=bvn_verification,
                user=None,
                status='success' if data.get('matched') else 'failed',
                face_match_score=data.get('similarity_score', 0.0),
                liveness_score=data.get('liveness_score', 0.0),
                verification_type='face_bvn',
                ip_address=data.get('ip_address', ''),
                device_info={'user_agent': data.get('user_agent', '')},
                completed_at=timezone.now()
            )
            
            logger.info(f"Verification created: {verification.id}")
            
            # Create audit log
            AuditLog.objects.create(
                user=None,
                client=client,
                action='create',
                model_name='Verification',
                record_id=str(verification.id),
                changes={
                    'verification_id': data.get('verification_id'),
                    'bvn': bvn,
                    'status': verification.status,
                    'face_match_score': verification.face_match_score,
                    'ip_address': data.get('ip_address', ''),
                    'source': 'fastapi_webhook'
                },
                ip_address=data.get('ip_address', ''),
                user_agent=data.get('user_agent', '')
            )
            
            # Charge client for verification (ONLY if successful and not already charged)
            # Check if already charged to prevent duplicates
            already_charged = Transaction.objects.filter(
                client=client,
                reference__icontains=f"VER_{verification.id[:8]}",
                transaction_type='verification_fee'
            ).exists()
            
            if verification.status == 'success' and not already_charged:
                try:
                    cost = verification.cost
                    
                    # Check if client has sufficient balance
                    if client.wallet.current_balance < cost:
                        logger.warning(f"Insufficient balance for {client.company_name}: {client.wallet.current_balance} < {cost}")
                        # Still return success but log the issue
                    
                    # Create transaction
                    transaction_obj = Transaction.objects.create(
                        client=client,
                        transaction_type='verification_fee',
                        amount=cost,
                        is_credit=False,
                        balance_before=client.wallet.current_balance,
                        balance_after=client.wallet.current_balance - cost,
                        reference=f"VER_{verification.id[:8]}_{bvn[-4:] if bvn else '0000'}",
                        description=f"Verification fee for BVN ending {bvn[-4:] if bvn else 'N/A'}",
                        status='completed',
                        created_by=None
                    )
                    
                    # Update wallet balance
                    client.wallet.current_balance -= cost
                    client.wallet.save()
                    
                    # Update total spent
                    client.total_spent = (client.total_spent or Decimal('0.00')) + cost
                    client.save(update_fields=['total_spent'])
                    
                    logger.info(f"Charged ${cost} to {client.company_name}")
                    
                except Exception as e:
                    logger.error(f"Billing error: {str(e)}")
                    # Don't fail the webhook if billing fails
                    # You might want to queue this for retry
            else:
                if already_charged:
                    logger.info(f"Skipping duplicate charge for verification {verification.id}")
        
        return JsonResponse({
            'status': 'success',
            'verification_id': verification.id,
            'message': 'Verification stored successfully'
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)