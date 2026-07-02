from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum
from import_export.admin import ImportExportModelAdmin
from .models import (
    User, Client, ClientWallet, Transaction,
    BVNVerification, Verification, AuditLog
)

class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'get_full_name', 'is_admin', 'is_client', 'is_active', 'created_at')
    list_filter = ('is_admin', 'is_client', 'is_active')
    search_fields = ('email', 'first_name', 'last_name', 'username')
    readonly_fields = ('created_at', 'updated_at', 'last_login')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Personal Info', {'fields': ('username', 'email', 'first_name', 'last_name', 'phone_number')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_admin', 'is_client', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )

class ClientWalletInline(admin.StackedInline):
    model = ClientWallet
    can_delete = False
    readonly_fields = ('current_balance', 'previous_balance', 'last_updated')
    extra = 0

class TransactionInline(admin.TabularInline):
    model = Transaction
    fields = ('reference', 'amount', 'is_credit', 'balance_before', 'balance_after', 'status', 'created_at')
    readonly_fields = fields
    can_delete = False
    extra = 0
    max_num = 10

class ClientAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'user_email', 'status', 'tier', 'balance_display', 'verifications_this_month', 'created_at')
    list_filter = ('status', 'tier', 'created_at')
    search_fields = ('company_name', 'user__email', 'user__first_name', 'user__last_name')
    readonly_fields = ('api_key', 'api_secret_display', 'created_at', 'updated_at')
    inlines = [ClientWalletInline, TransactionInline]
    
    fieldsets = (
        ('Company Information', {'fields': ('company_name', 'user', 'status', 'tier')}),
        ('API Credentials', {'fields': ('api_key', 'api_secret_display')}),
        ('Verification Limits', {'fields': ('monthly_verification_limit', 'verifications_this_month')}),
        ('Webhook', {'fields': ('webhook_url',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )
    
    def user_email(self, obj):
        return obj.user.email if obj.user else '-'
    user_email.short_description = 'Email'
    user_email.admin_order_field = 'user__email'
    
    def balance_display(self, obj):
        if hasattr(obj, 'wallet'):
            color = 'green' if obj.balance > 0 else 'red'
            return format_html(
                '<span style="color: {}; font-weight: bold;">${:.2f}</span>',
                color, obj.balance
            )
        return format_html('<span style="color: gray;">$0.00</span>')
    balance_display.short_description = 'Balance'
    balance_display.admin_order_field = 'wallet__current_balance'
    
    def api_secret_display(self, obj):
        return '************'
    api_secret_display.short_description = 'API Secret'

class TransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'client', 'amount_display', 'transaction_type', 'status', 'created_at')
    list_filter = ('transaction_type', 'is_credit', 'status', 'created_at')
    search_fields = ('reference', 'client__company_name', 'client__user__email', 'description')
    readonly_fields = ('reference', 'balance_before', 'balance_after', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    
    def amount_display(self, obj):
        color = 'green' if obj.is_credit else 'red'
        sign = '+' if obj.is_credit else '-'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}${:.2f}</span>',
            color, sign, obj.amount
        )
    amount_display.short_description = 'Amount'

class BVNVerificationAdmin(admin.ModelAdmin):
    list_display = ('id_short', 'client', 'status', 'hash_bvn_short', 'first_name', 'last_name', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('hash_bvn', 'first_name', 'last_name', 'bvn', 'client__company_name')
    readonly_fields = ('hash_bvn', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Client', {'fields': ('client', 'hash_bvn', 'status')}),
        ('BVN Data', {'fields': ('bvn', 'first_name', 'last_name', 'middle_name', 'date_of_birth', 'phone_number')}),
        ('Bank Details', {'fields': ('bank_name', 'bank_code', 'account_number')}),
        ('Verification Metadata', {'fields': ('request_data', 'response_data', 'error_message', 'verified_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )
    
    def id_short(self, obj):
        return obj.id[:8] if obj.id else '-'
    id_short.short_description = 'ID'
    
    def hash_bvn_short(self, obj):
        return f"{obj.hash_bvn[:10]}..." if obj.hash_bvn else '-'
    hash_bvn_short.short_description = 'BVN Hash'

class VerificationAdmin(admin.ModelAdmin):
    list_display = ('id_short', 'client', 'status', 'verification_type', 'face_match_score', 'liveness_score', 'started_at')
    list_filter = ('status', 'verification_type', 'started_at')
    search_fields = ('id', 'client__company_name', 'user__email')
    readonly_fields = ('started_at',)
    
    fieldsets = (
        ('Client & User', {'fields': ('client', 'user', 'bvn_verification')}),
        ('Verification Status', {'fields': ('status', 'verification_type', 'face_match_score', 'liveness_score')}),
        ('Media', {'fields': ('selfie_image', 'id_image', 'video')}),
        ('Metadata', {'fields': ('ip_address', 'device_info', 'location_data', 'completed_at')}),
    )
    
    def id_short(self, obj):
        return obj.id[:8] if obj.id else '-'
    id_short.short_description = 'ID'

class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'model_name', 'record_id', 'client', 'created_at')
    list_filter = ('action', 'model_name', 'created_at')
    search_fields = ('user__email', 'record_id', 'model_name')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

# Register all models
admin.site.register(User, UserAdmin)
admin.site.register(Client, ClientAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(BVNVerification, BVNVerificationAdmin)
admin.site.register(Verification, VerificationAdmin)
admin.site.register(AuditLog, AuditLogAdmin)