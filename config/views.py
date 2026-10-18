from datetime import timedelta
from decimal import Decimal

from django.contrib.staticfiles import finders
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from products.models import Category, Product

# Categories have no icon or tagline in the database yet,
# so we match them by slug. Unknown categories get a default.
CATEGORY_STYLES = {
    'skincare': {'icon': '🧴', 'tagline': 'Radiant, healthy skin', 'css_class': 'cat-skincare', 'image': 'images/skin.jpg.jpeg'},
    'makeup':   {'icon': '💄', 'tagline': 'Colour that empowers', 'css_class': 'cat-makeup', 'image': 'images/make.jpg.jpeg'},
    'perfumes': {'icon': '🌸', 'tagline': 'Signature scents', 'css_class': 'cat-perfumes', 'image': 'images/perf.jpg.jpeg'},
    'haircare': {'icon': '💆‍♀️', 'tagline': 'Silky, shiny, strong', 'css_class': 'cat-haircare', 'image': 'images/hair.jpg.jpeg'},
    'bodycare': {'icon': '🛁', 'tagline': 'Soft, smooth skin', 'css_class': 'cat-bodycare', 'image': 'images/body.jpg.jpeg'},
}
DEFAULT_ICON = '✨'
DEFAULT_TAGLINE = 'Explore the collection'
FALLBACK_CLASSES = ['cat-skincare', 'cat-makeup', 'cat-perfumes', 'cat-haircare']


def format_price(price):
    """2450.00 -> '2,450'   and   649.50 -> '649.50'"""
    if price == price.to_integral_value():
        return f'{price:,.0f}'
    return f'{price:,.2f}'


def home(request):
    """Homepage: real categories and featured products from the database."""

    # ----- Categories -----
    categories = []
    for index, category in enumerate(Category.objects.filter(is_active=True)[:8]):
        style = CATEGORY_STYLES.get(category.slug, {})
        category_data = {
            'name': category.name,
            'tagline': style.get('tagline') or category.description[:40] or DEFAULT_TAGLINE,
            'icon': style.get('icon', DEFAULT_ICON),
            'css_class': style.get('css_class', FALLBACK_CLASSES[index % 4]),
            'url': reverse('products:category', args=[category.slug]),
        }
        image_path = style.get('image')
        if image_path and finders.find(image_path):
            category_data['image'] = image_path
        categories.append(category_data)

    # ----- Featured products -----
    available = Product.objects.filter(is_available=True).select_related('category')
    products = list(available.filter(is_featured=True)[:4])

    # If nothing is ticked "featured" yet, show the newest products instead
    if not products:
        products = list(available[:4])

    new_since = timezone.now() - timedelta(days=14)
    featured_products = []
    for product in products:
        if not product.in_stock:
            badge = 'Out of stock'
        elif product.created_at >= new_since:
            badge = 'New'
        else:
            badge = ''

        featured_products.append({
            'name': product.name,
            'category': product.category.name,
            'price': format_price(Decimal(product.price)),
            'icon': '✨',
            'badge': badge,
            'image': product.image.url if product.image else '',
            'url': reverse('products:detail', args=[product.slug]),
        })

    context = {
        'categories': categories,
        'featured_products': featured_products,
    }
    return render(request, 'home.html', context)