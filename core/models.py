from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid
import hashlib
import secrets
from decimal import Decimal

class User(AbstractUser):
    """Custom user model for admin and client users"""
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    is_client = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_client']),
        ]
    
    def __str__(self):
        return f"{self.email} - {self.get_full_name()}"


class Client(models.Model):
    """Client (Bank/Customer) model"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
    ]
    
    TIER_CHOICES = [
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('enterprise', 'Enterprise'),
    ]
    
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_profile')
    company_name = models.CharField(max_length=255)
    api_key = models.CharField(max_length=100, unique=True, editable=False)
    api_secret = models.CharField(max_length=255, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='basic')
    monthly_verification_limit = models.IntegerField(default=1000)
    verifications_this_month = models.IntegerField(default=0)
    webhook_url = models.URLField(blank=True, null=True)
    total_spent = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total amount spent by this client"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'clients'
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.api_key:
            # Generate API credentials
            self.api_key = f"fv_{secrets.token_urlsafe(24)}"
            raw_secret = secrets.token_urlsafe(32)
            self.api_secret = hashlib.sha256(raw_secret.encode()).hexdigest()
            self._raw_api_secret = raw_secret
        super().save(*args, **kwargs)
    
    def get_raw_api_secret(self):
        return getattr(self, '_raw_api_secret', None)
    
    @property
    def balance(self):
        try:
            return self.wallet.current_balance
        except ClientWallet.DoesNotExist:
            return Decimal('0.00')
    
    def calculate_total_spent(self):
        """Calculate total spent from all debit transactions"""
        total = self.transactions.filter(
            is_credit=False,
            status='completed'
        ).aggregate(
            total=models.Sum('amount')
        )['total']
        return total or Decimal('0.00')
    
    def update_total_spent(self):
        """Update total_spent based on transaction history"""
        self.total_spent = self.calculate_total_spent()
        self.save(update_fields=['total_spent'])
    
    def __str__(self):
        return f"{self.company_name} - {self.user.email}"


class ClientWallet(models.Model):
    """Client wallet model - tracks balances"""
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='wallet')
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    previous_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'client_wallets'
    
    def update_balance(self, amount, is_credit=True):
        """Update wallet balance with transaction"""
        self.previous_balance = self.current_balance
        if is_credit:
            self.current_balance += Decimal(str(amount))
        else:
            if self.current_balance < Decimal(str(amount)):
                raise ValueError("Insufficient balance")
            self.current_balance -= Decimal(str(amount))
        self.save()
        return self.current_balance
    
    def __str__(self):
        return f"{self.client.company_name} - Balance: {self.current_balance}"


class Transaction(models.Model):
    """Wallet transaction history"""
    TRANSACTION_TYPES = [
        ('funding', 'Funding'),
        ('verification_fee', 'Verification Fee'),
        ('refund', 'Refund'),
        ('adjustment', 'Adjustment'),
    ]
    
    TRANSACTION_STATUS = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('reversed', 'Reversed'),
    ]
    
    PAYMENT_METHODS = [
        ('manual', 'Manual'),
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
        ('credit_card', 'Credit Card'),
    ]
    
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    is_credit = models.BooleanField(default=True)
    balance_before = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    reference = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='pending')
    account_number = models.CharField(max_length=20, blank=True, null=True)
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default='manual',
        blank=True
    )
    reference_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="External reference ID (e.g., Stripe payment intent ID, PayPal transaction ID)"
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_transactions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'wallet_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_method']),
            models.Index(fields=['reference_id']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.reference:
            prefix = 'FUND' if self.is_credit else 'DEBIT'
            self.reference = f"{prefix}_{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)
    
    def process_payment(self):
        """Process payment based on payment method"""
        if self.payment_method == 'stripe':
            # Stripe payment processing logic
            pass
        elif self.payment_method == 'paypal':
            # PayPal payment processing logic
            pass
        elif self.payment_method == 'bank_transfer':
            # Bank transfer processing logic
            pass
        # ... etc
    
    def __str__(self):
        return f"{self.reference} - {self.client.company_name} - {self.amount}"


class BVNVerification(models.Model):
    """BVN verification data"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('not_found', 'Not Found'),
    ]
    
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='bvn_verifications')
    hash_bvn = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # BVN Data (encrypted in production)
    bvn = models.CharField(max_length=20, blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_code = models.CharField(max_length=10, blank=True, null=True)
    account_number = models.CharField(max_length=20, blank=True, null=True)
    
    # Verification metadata
    request_data = models.JSONField(blank=True, null=True)
    response_data = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'bvn_verifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['hash_bvn', 'status']),
        ]
    
    def __str__(self):
        return f"BVN {self.hash_bvn[:10]}... - {self.status}"


class Verification(models.Model):
    """Face verification record"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('rejected', 'Rejected'),
    ]
    
    VERIFICATION_TYPES = [
        ('face_bvn', 'Face + BVN'),
    ]
    
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='verifications')
    bvn_verification = models.ForeignKey(BVNVerification, on_delete=models.SET_NULL, null=True, related_name='verifications')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='verifications')
    
    # Verification status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    face_match_score = models.FloatField(blank=True, null=True)
    liveness_score = models.FloatField(blank=True, null=True)
    verification_type = models.CharField(max_length=50, choices=VERIFICATION_TYPES)
    
    # Media files
    selfie_image = models.URLField(blank=True, null=True)
    id_image = models.URLField(blank=True, null=True)
    video = models.URLField(blank=True, null=True)
    
    # Metadata
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    device_info = models.JSONField(blank=True, null=True)
    location_data = models.JSONField(blank=True, null=True)
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'verifications'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['client', 'status']),
            models.Index(fields=['-started_at']),
        ]
    
    @property
    def cost(self):
        """Calculate verification cost based on type"""
        costs = {
            'face_bvn': Decimal('100.00'),
            'face_only': Decimal('30.00'),
            'face_nin': Decimal('75.00'),
        }
        return costs.get(self.verification_type, Decimal('0.00'))
    
    def __str__(self):
        return f"Verification {self.id[:8]} - {self.status}"


class AuditLog(models.Model):
    """Audit trail for all admin actions"""
    ACTION_TYPES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('fund', 'Fund'),
        ('view', 'View'),
        ('export', 'Export'),
        ('login', 'Login'),
        ('logout', 'Logout'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    model_name = models.CharField(max_length=100)
    record_id = models.CharField(max_length=100)
    changes = models.JSONField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email if self.user else 'System'} - {self.action} - {self.model_name}"


# Signal to automatically update total_spent when transactions are created/updated
@receiver(post_save, sender=Transaction)
def update_client_total_spent(sender, instance, created, **kwargs):
    """Update client's total_spent when a new debit transaction is completed"""
    if not instance.is_credit and instance.status == 'completed':
        # Update total_spent for the client
        instance.client.update_total_spent()
    elif instance.status == 'completed' and not instance.is_credit:
        # Also update if a pending transaction is marked as completed
        instance.client.update_total_spent()