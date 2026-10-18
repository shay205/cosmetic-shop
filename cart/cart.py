from products.models import Product

CART_SESSION_ID = 'cart'


class Cart:
    """A shopping cart stored in the visitor's session.

    It only remembers {product id: quantity}. Names, prices and stock are
    always read fresh from the database, so the cart never shows old prices.
    """

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_ID)
        if cart is None:
            cart = self.session[CART_SESSION_ID] = {}
        self.cart = cart

    def save(self):
        # Tell Django the session changed so it gets saved
        self.session.modified = True

    def add(self, product, quantity=1):
        """Add a product. Never goes above the stock we have.

        Returns (quantity now in cart, True if we had to limit it).
        """
        product_id = str(product.id)
        wanted = self.cart.get(product_id, 0) + quantity
        new_quantity = min(wanted, product.stock_quantity)

        if new_quantity > 0:
            self.cart[product_id] = new_quantity
            self.save()
        return new_quantity, wanted > product.stock_quantity

    def update(self, product, quantity):
        """Set an exact quantity (used on the cart page).

        Returns (quantity now in cart, True if we had to limit it).
        """
        product_id = str(product.id)
        new_quantity = min(quantity, product.stock_quantity)

        if new_quantity > 0:
            self.cart[product_id] = new_quantity
        else:
            self.cart.pop(product_id, None)
        self.save()
        return max(new_quantity, 0), quantity > product.stock_quantity

    def remove(self, product):
        """Take a product out of the cart."""
        self.cart.pop(str(product.id), None)
        self.save()

    def clear(self):
        """Empty the cart (used after an order is placed, later)."""
        self.session.pop(CART_SESSION_ID, None)
        self.save()

    def __iter__(self):
        """Loop over the cart: each item has a product, quantity and line total."""
        ids = list(self.cart.keys())
        products = Product.objects.filter(
            id__in=ids, is_available=True
        ).select_related('category')
        found = {str(product.id): product for product in products}

        # Quietly drop products that were deleted or switched off in the admin
        missing = [product_id for product_id in ids if product_id not in found]
        if missing:
            for product_id in missing:
                del self.cart[product_id]
            self.save()

        for product_id in ids:
            if product_id in found:
                product = found[product_id]
                quantity = self.cart[product_id]
                yield {
                    'product': product,
                    'quantity': quantity,
                    'line_total': product.price * quantity,
                    # True if stock dropped below what's in the cart
                    'over_stock': quantity > product.stock_quantity,
                }

    def __len__(self):
        """Total number of items (used for the number on the navbar cart icon)."""
        return sum(self.cart.values())

    def get_total_price(self):
        return sum(item['line_total'] for item in self)