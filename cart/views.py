from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from products.models import Product

from .cart import Cart


def _read_quantity(request, default=1):
    """Read the 'quantity' value from a form safely. Bad input gives the default."""
    try:
        return int(request.POST.get('quantity', default))
    except (TypeError, ValueError):
        return default


def cart_detail(request):
    """The cart page: every item, its quantity and the total."""
    cart = Cart(request)
    context = {
        'cart': cart,
        'items': list(cart),
        'total': cart.get_total_price(),
    }
    return render(request, 'cart/cart_detail.html', context)


@require_POST
def cart_add(request, product_id):
    """Add a product to the cart (from the Add to Cart button)."""
    product = get_object_or_404(Product, id=product_id, is_available=True)
    cart = Cart(request)

    if not product.in_stock:
        messages.error(request, f'Sorry, {product.name} is out of stock.')
        return redirect('products:detail', slug=product.slug)

    quantity = max(_read_quantity(request), 1)
    new_quantity, limited = cart.add(product, quantity)

    if limited:
        messages.warning(
            request,
            f'We only have {product.stock_quantity} of {product.name} in stock, '
            f'so your cart now holds {new_quantity}.'
        )
    else:
        messages.success(request, f'{product.name} was added to your cart.')
    return redirect('cart:detail')


@require_POST
def cart_update(request, product_id):
    """Change a quantity on the cart page. A quantity of 0 removes the item."""
    product = get_object_or_404(Product, id=product_id)
    cart = Cart(request)

    quantity = max(_read_quantity(request, default=1), 0)
    new_quantity, limited = cart.update(product, quantity)

    if new_quantity == 0:
        messages.success(request, f'{product.name} was removed from your cart.')
    elif limited:
        messages.warning(
            request,
            f'We only have {product.stock_quantity} of {product.name} in stock, '
            f'so the quantity was set to {new_quantity}.'
        )
    else:
        messages.success(request, 'Your cart was updated.')
    return redirect('cart:detail')


@require_POST
def cart_remove(request, product_id):
    """Remove a product from the cart."""
    product = get_object_or_404(Product, id=product_id)
    Cart(request).remove(product)
    messages.success(request, f'{product.name} was removed from your cart.')
    return redirect('cart:detail')