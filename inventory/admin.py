from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError

from .models import InventoryMovement
from .services import record_stock_movement


class InventoryMovementAdminForm(forms.ModelForm):
    class Meta:
        model = InventoryMovement
        fields = ('product', 'quantity_change', 'reason', 'notes')

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity_change = cleaned_data.get('quantity_change')

        if product is not None and quantity_change is not None:
            if product.stock_quantity + quantity_change < 0:
                raise ValidationError(
                    f'Stock for {product.name} cannot be reduced below zero.'
                )
        return cleaned_data


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    form = InventoryMovementAdminForm
    list_display = ('product', 'reason', 'quantity_change', 'stock_after', 'created_at')
    list_filter = ('reason', 'created_at')
    search_fields = ('product__name', 'notes')
    readonly_fields = ('order_item', 'stock_after', 'created_at')
    fields = (
        'product', 'quantity_change', 'reason', 'notes',
        'order_item', 'stock_after', 'created_at',
    )

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change:
            raise ValidationError('Inventory movement records cannot be edited.')

        movement = record_stock_movement(
            product=obj.product,
            quantity_change=obj.quantity_change,
            reason=obj.reason,
            notes=obj.notes,
        )
        obj.pk = movement.pk
        obj.stock_after = movement.stock_after
        obj.created_at = movement.created_at
