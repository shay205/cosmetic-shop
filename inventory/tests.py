from django.test import TestCase

from django.core.exceptions import ValidationError

from products.models import Category, Product

from .models import InventoryMovement
from .services import record_stock_movement


class InventoryMovementTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Skincare')
        self.product = Product.objects.create(
            category=category,
            name='Rose Serum',
            price='1200.00',
            stock_quantity=3,
        )

    def test_movement_updates_stock_and_records_balance(self):
        movement = record_stock_movement(
            self.product,
            quantity_change=5,
            reason='restock',
            notes='New stock delivery',
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)
        self.assertEqual(movement.stock_after, 8)
        self.assertEqual(movement.quantity_change, 5)

    def test_movement_cannot_reduce_stock_below_zero(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(
                self.product,
                quantity_change=-4,
                reason='sale',
            )

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)
        self.assertEqual(InventoryMovement.objects.count(), 0)
