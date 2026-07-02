from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from .models import Client, User, Verification, Transaction
from decimal import Decimal

User = get_user_model()

class LoginForm(AuthenticationForm):
    """Custom login """
    username = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email address',
            'autofocus': True
        }),
        label="Email Address"
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        }),
        label="Password"
    )
    
    error_messages = {
        'invalid_login': "Please enter a valid email and password.",
        'inactive': "This account is inactive.",
    }

class ClientForm(forms.ModelForm):
    """Form for creating a new client"""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'client@company.com'
        }),
        label="Email Address"
    )
    first_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'John'
        }),
        label="First Name"
    )
    last_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Doe'
        }),
        label="Last Name"
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter password'
        }),
        required=True,
        label="Password",
        help_text="Minimum 8 characters"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password'
        }),
        required=True,
        label="Confirm Password"
    )
    
    class Meta:
        model = Client
        fields = ['company_name', 'tier', 'monthly_verification_limit', 'webhook_url']
        widgets = {
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Acme Corp'
            }),
            'tier': forms.Select(attrs={'class': 'form-control'}),
            'monthly_verification_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'value': 1000
            }),
            'webhook_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com/webhook'
            }),
        }
        labels = {
            'company_name': 'Company Name',
            'tier': 'Subscription Tier',
            'monthly_verification_limit': 'Monthly Verification Limit',
            'webhook_url': 'Webhook URL (Optional)',
        }
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        if len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters long.')
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')
        
        return cleaned_data

class ClientEditForm(forms.ModelForm):
    """Form for editing existing client"""
    class Meta:
        model = Client
        fields = ['company_name', 'status', 'tier', 'monthly_verification_limit', 'webhook_url']
        widgets = {
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Company Name'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'tier': forms.Select(attrs={'class': 'form-control'}),
            'monthly_verification_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1
            }),
            'webhook_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com/webhook'
            }),
        }
        labels = {
            'company_name': 'Company Name',
            'status': 'Account Status',
            'tier': 'Subscription Tier',
            'monthly_verification_limit': 'Monthly Verification Limit',
            'webhook_url': 'Webhook URL',
        }

class FundClientForm(forms.Form):
    """Form for funding a client's wallet"""
    amount = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': '0.00'
        }),
        label="Amount to Fund ($)"
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'form-control',
            'placeholder': 'Funding description (optional)'
        }),
        required=False,
        label="Description"
    )
    account_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Bank account number (optional)'
        }),
        label="Account Number (Optional)"
    )
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount <= 0:
            raise forms.ValidationError('Amount must be greater than zero.')
        if amount > 1000000:
            raise forms.ValidationError('Maximum funding amount is $1,000,000.')
        return amount

class VerificationReportForm(forms.Form):
    """Form for generating verification reports"""
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        required=True,
        label="Start Date"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        required=True,
        label="End Date"
    )
    client = forms.ModelChoiceField(
        queryset=Client.objects.all().order_by('company_name'),
        required=False,
        empty_label="All Clients",
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Filter by Client"
    )
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + list(Verification.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Filter by Status"
    )
    format = forms.ChoiceField(
        choices=[('html', 'HTML Preview'), ('csv', 'CSV Export')],
        initial='html',
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Report Format"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError('Start date must be before end date.')
            
            # Limit date range to 90 days
            if (end_date - start_date).days > 90:
                raise forms.ValidationError('Date range cannot exceed 90 days.')
        
        return cleaned_data

class UserProfileForm(forms.ModelForm):
    """Form for editing user profile"""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last Name'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+1234567890'
            }),
        }
        labels = {
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'phone_number': 'Phone Number',
        }

class ChangePasswordForm(forms.Form):
    """Form for changing user password"""
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Current password'
        }),
        label="Current Password"
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'New password'
        }),
        label="New Password",
        help_text="Minimum 8 characters"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password'
        }),
        label="Confirm New Password"
    )
    
    def clean_new_password(self):
        password = self.cleaned_data.get('new_password')
        if len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters long.')
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')
        
        return cleaned_data
    

class FundClientForm(forms.Form):
    amount = forms.DecimalField(
        min_value=0.01,
        max_value=999999.99,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0.00',
            'step': '0.01'
        }),
        label='Amount'
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add a note for this transaction...'
        }),
        label='Notes'
    )
    
    payment_method = forms.ChoiceField(
        choices=Transaction.PAYMENT_METHODS,
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
        label='Payment Method'
    )
    
    reference_id = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'External reference ID'
        }),
        label='Reference ID'
    )
    
    def __init__(self, *args, **kwargs):
        self.client_id = kwargs.pop('client_id', None)
        super().__init__(*args, **kwargs)