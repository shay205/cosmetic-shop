from django.core.exceptions import ValidationError
from django.db import models


class InventoryMovement(models.Model):
    """A recorded stock change; use the inventory service to create movements."""

    REASON_CHOICES = [
        ('restock', 'Restock'),
        ('sale', 'Sale'),
        ('adjustment', 'Adjustment'),
    ]

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='inventory_movements',
    )
    order_item = models.ForeignKey(
        'sales.OrderItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_movements',
    )
    quantity_change = models.IntegerField(
        help_text='Use a positive number to add stock and a negative number to remove it.'
    )
    stock_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return f'{self.product.name}: {self.quantity_change:+d} ({self.get_reason_display()})'

    def clean(self):
        if self.quantity_change == 0:
            raise ValidationError({'quantity_change': 'A stock movement cannot be zero.'})
        if self.reason == 'restock' and self.quantity_change < 0:
            raise ValidationError({'quantity_change': 'A restock must add stock.'})
        if self.reason == 'sale' and self.quantity_change > 0:
            raise ValidationError({'quantity_change': 'A sale must remove stock.'})
