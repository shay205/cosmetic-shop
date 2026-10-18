"""Create temporary illustrated product images for demonstrations.

Usage:
    python manage.py add_demo_images                        add images
    python manage.py add_demo_images --add-bodycare-sample  also add one sample Bodycare product
    python manage.py add_demo_images --remove               undo: remove demo images

Safe to run more than once. Products that already have an image
(real uploads included) are never touched.
"""
import shutil
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from products.models import Category, Product

DEMO_DIR = 'products/demo'   # inside MEDIA_ROOT
FINAL = 800                  # final image size in pixels
S = FINAL * 2                # drawn at double size, then shrunk, for smooth edges

TOP = (251, 227, 234)        # blush
BOTTOM = (233, 224, 247)     # lavender
CREAM = (255, 248, 240)
INK = (45, 34, 48)
GOLD = (214, 178, 120)
ACCENTS = [(212, 120, 143), (183, 163, 217), (232, 160, 180), (160, 130, 200)]


# ---------- small drawing helpers (coordinates are 0-100, like percentages) ----------
def px(v):
    return v * S / 100


def box(x0, y0, x1, y1):
    return [px(x0), px(y0), px(x1), px(y1)]


def lighten(color, t):
    return tuple(int(v + (255 - v) * t) for v in color)


def darken(color, t):
    return tuple(int(v * (1 - t)) for v in color)


def rounded(d, coords, radius, fill):
    d.rounded_rectangle(box(*coords), radius=px(radius), fill=fill)


def rect(d, coords, fill):
    d.rectangle(box(*coords), fill=fill)


def poly(d, points, fill):
    d.polygon([(px(x), px(y)) for x, y in points], fill=fill)


def sparkle(d, cx, cy, r):
    k = r * 0.25
    poly(d, [(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
             (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)], CREAM)


# ---------- one drawing per category ----------
def draw_skincare(d, accent):          # dropper bottle
    rounded(d, (44, 8, 56, 26), 6, darken(accent, 0.15))     # rubber bulb
    rect(d, (42, 30, 58, 38), darken(accent, 0.25))          # neck
    rounded(d, (39, 25, 61, 32), 2, GOLD)                    # collar
    rounded(d, (30, 38, 70, 88), 7, accent)                  # bottle
    rounded(d, (34, 44, 39, 80), 2.5, lighten(accent, 0.45)) # shine
    rounded(d, (43, 56, 66, 76), 3, CREAM)                   # label


def draw_makeup(d, accent):            # lipstick
    rounded(d, (37, 56, 63, 90), 3, INK)
    rect(d, (37, 50, 63, 57), GOLD)
    rect(d, (40, 36, 60, 50), darken(GOLD, 0.15))
    poly(d, [(42, 36), (42, 24), (58, 10), (58, 36)], accent)
    poly(d, [(44, 34), (44, 26), (47, 23), (47, 34)], lighten(accent, 0.4))


def draw_haircare(d, accent):          # pump bottle
    rect(d, (46, 28, 54, 38), darken(accent, 0.25))
    rounded(d, (40, 18, 60, 28), 3, INK)
    rect(d, (58, 20, 74, 25), INK)
    rounded(d, (31, 36, 69, 91), 9, accent)
    rounded(d, (35, 42, 40, 84), 2.5, lighten(accent, 0.45))
    rounded(d, (42, 54, 64, 78), 3, CREAM)


def draw_perfumes(d, accent):          # perfume flask
    rounded(d, (40, 12, 60, 32), 4, GOLD)
    rect(d, (44, 30, 56, 42), darken(GOLD, 0.25))
    rounded(d, (27, 40, 73, 89), 11, lighten(accent, 0.15))
    rounded(d, (31, 46, 37, 82), 3, lighten(accent, 0.6))
    rounded(d, (38, 58, 64, 76), 3, CREAM)


def draw_bodycare(d, accent):          # lotion tube standing on its cap
    poly(d, [(32, 16), (68, 16), (64, 80), (36, 80)], accent)
    rect(d, (32, 9, 68, 17), darken(accent, 0.25))
    for i in range(5):
        rect(d, (34 + i * 7, 10, 35.5 + i * 7, 16), darken(accent, 0.4))
    poly(d, [(36, 20), (39, 20), (41, 76), (38, 76)], lighten(accent, 0.45))
    rounded(d, (41, 34, 59, 62), 3, CREAM)
    rounded(d, (37, 79, 63, 92), 3, CREAM)


DRAWERS = {
    'skincare': draw_skincare,
    'makeup': draw_makeup,
    'haircare': draw_haircare,
    'perfumes': draw_perfumes,
    'bodycare': draw_bodycare,
}


def make_image(category_slug, accent):
    img = Image.new('RGB', (S, S), TOP)
    d = ImageDraw.Draw(img)
    for y in range(S):                                   # soft blush-to-lavender background
        t = y / (S - 1)
        d.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    d.ellipse(box(8, 8, 92, 92), fill=lighten(TOP, 0.55))      # soft glow behind the product
    d.ellipse(box(25, 88, 75, 95), fill=darken(BOTTOM, 0.12))  # shadow under the product
    DRAWERS[category_slug](d, accent)
    sparkle(d, 19, 24, 5)
    sparkle(d, 82, 66, 3.5)
    return img.resize((FINAL, FINAL), Image.LANCZOS)


class Command(BaseCommand):
    help = 'Add (or remove) temporary illustrated demo images for products.'

    def add_arguments(self, parser):
        parser.add_argument('--remove', action='store_true',
                            help='Remove the demo images and clear them from products.')
        parser.add_argument('--add-bodycare-sample', action='store_true',
                            help='Also create one sample Bodycare product if Bodycare has none.')

    def handle(self, *args, **options):
        if options['remove']:
            self.remove_demo_images()
        else:
            self.add_demo_images(options['add_bodycare_sample'])

    def add_demo_images(self, add_sample):
        bodycare, created = Category.objects.get_or_create(
            slug='bodycare', defaults={'name': 'Bodycare'})
        if created:
            self.stdout.write('Created category: Bodycare')

        if add_sample and not bodycare.products.exists():
            sample, made = Product.objects.get_or_create(
                name='Shea Butter Body Lotion',
                defaults={'category': bodycare, 'price': Decimal('1500'), 'stock_quantity': 10},
            )
            if made:
                self.stdout.write('Created sample product: Shea Butter Body Lotion '
                                  '(placeholder price: edit or delete it in the admin)')

        added = kept = 0
        for index, product in enumerate(Product.objects.select_related('category').order_by('id')):
            if product.image:
                self.stdout.write(f'Kept existing image: {product.name}')
                kept += 1
                continue

            slug = product.category.slug
            if slug not in DRAWERS:
                self.stdout.write(self.style.WARNING(
                    f'Skipped {product.name}: no demo drawing for category "{product.category.name}"'))
                continue

            relative = f'{DEMO_DIR}/{slug}/{product.slug}.png'
            target = Path(settings.MEDIA_ROOT) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            make_image(slug, ACCENTS[index % len(ACCENTS)]).save(target, 'PNG', optimize=True)

            product.image.name = relative
            product.save(update_fields=['image', 'updated_at'])
            self.stdout.write(f'Added demo image: {product.name}  ->  media/{relative}')
            added += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. {added} demo image(s) added, {kept} existing image(s) kept.'))

    def remove_demo_images(self):
        count = 0
        for product in Product.objects.filter(image__startswith=f'{DEMO_DIR}/'):
            product.image = ''
            product.save(update_fields=['image', 'updated_at'])
            count += 1

        folder = Path(settings.MEDIA_ROOT) / DEMO_DIR
        if folder.exists():
            shutil.rmtree(folder)
        self.stdout.write(self.style.SUCCESS(f'Removed demo images from {count} product(s).'))