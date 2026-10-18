from django.core.exceptions import ValidationError
from django.db import transaction

from products.models import Product

from .models import InventoryMovement


@transaction.atomic
def record_stock_movement(product, quantity_change, reason, notes='', order_item=None):
    """Update a product's stock and append its audit record atomically."""
    try:
        quantity_change = int(quantity_change)
    except (TypeError, ValueError) as error:
        raise ValidationError('Enter a whole-number stock change.') from error

    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    new_stock = locked_product.stock_quantity + quantity_change
    if new_stock < 0:
        raise ValidationError(
            f'Stock for {locked_product.name} cannot be reduced below zero.'
        )

    movement = InventoryMovement(
        product=locked_product,
        order_item=order_item,
        quantity_change=quantity_change,
        stock_after=new_stock,
        reason=reason,
        notes=notes,
    )
    movement.full_clean()
    locked_product.stock_quantity = new_stock
    locked_product.save(update_fields=['stock_quantity', 'updated_at'])
    movement.save()
    return movement
