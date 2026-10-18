from django.contrib import admin
from django.db import transaction

from inventory.models import InventoryMovement
from inventory.services import record_stock_movement

from .models import MpesaPayment, Order, OrderItem


def _restore_cancelled_order_stock(order):
    note = f'Order cancellation {order.order_number}'
    for item in order.items.select_related('product'):
        if not item.product_id or InventoryMovement.objects.filter(
            order_item=item,
            reason='adjustment',
            quantity_change=item.quantity,
            notes=note,
        ).exists():
            continue
        record_stock_movement(
            product=item.product,
            quantity_change=item.quantity,
            reason='adjustment',
            notes=note,
            order_item=item,
        )


class OrderItemInline(admin.TabularInline):
    """Shows the products inside an order, on the order's own page."""

    model = OrderItem
    extra = 0
    can_delete = False
    fields = ('product_name', 'price', 'quantity')
    readonly_fields = ('product_name', 'price', 'quantity')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'full_name', 'phone', 'city', 'total',
                    'status', 'created_at')
    list_filter = ('status', 'created_at', 'city')
    list_editable = ('status',)
    search_fields = ('full_name', 'email', 'phone', 'id')
    date_hierarchy = 'created_at'
    readonly_fields = ('order_number', 'user', 'total', 'created_at', 'updated_at')
    inlines = [OrderItemInline]

    fieldsets = (
        ('Order', {'fields': ('order_number', 'status', 'total', 'created_at', 'updated_at')}),
        ('Customer', {'fields': ('user', 'full_name', 'email', 'phone')}),
        ('Delivery', {'fields': ('address', 'city', 'notes')}),
    )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            previous_status = None
            if change:
                previous_status = Order.objects.values_list(
                    'status', flat=True
                ).get(pk=obj.pk)
            super().save_model(request, obj, form, change)
            if previous_status != 'cancelled' and obj.status == 'cancelled':
                _restore_cancelled_order_stock(obj)


@admin.register(MpesaPayment)
class MpesaPaymentAdmin(admin.ModelAdmin):
    list_display = ('order', 'phone_number', 'amount', 'status', 'receipt_number', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order__id', 'phone_number', 'checkout_request_id', 'receipt_number')
    readonly_fields = (
        'order', 'phone_number', 'amount', 'status', 'merchant_request_id',
        'checkout_request_id', 'receipt_number', 'result_code',
        'result_description', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False