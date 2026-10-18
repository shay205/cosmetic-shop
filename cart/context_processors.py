from .cart import Cart


def cart(request):
    """Make the cart available in every template as {{ cart }}.

    This lets the navbar show the live item count on any page.
    """
    return {'cart': Cart(request)}