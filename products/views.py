from django.shortcuts import get_object_or_404, render

from .models import Category, Product


def search(request):
    """Search available products by name, using the ?q= value from the search bar."""
    query = request.GET.get('q', '').strip()
    products = Product.objects.none()

    if query:
        products = (
            Product.objects
            .filter(name__icontains=query, is_available=True)
            .select_related('category')
        )

    context = {
        'query': query,
        'products': products,
    }
    return render(request, 'products/search_results.html', context)


def category_detail(request, slug):
    """Show all available products in one category, e.g. /category/skincare/."""
    category = get_object_or_404(Category, slug=slug, is_active=True)
    products = (
        Product.objects
        .filter(category=category, is_available=True)
        .select_related('category')
    )
    context = {
        'category': category,
        'products': products,
    }
    return render(request, 'products/category_detail.html', context)


def product_detail(request, slug):
    """Show one product, e.g. /product/rose-glow-face-serum/."""
    product = get_object_or_404(
        Product.objects.select_related('category'),
        slug=slug,
        is_available=True,
    )
    # Up to 4 other available products from the same category
    related_products = (
        Product.objects
        .filter(category=product.category, is_available=True)
        .exclude(pk=product.pk)
        .select_related('category')[:4]
    )
    context = {
        'product': product,
        'related_products': related_products,
    }
    return render(request, 'products/product_detail.html', context)