from decimal import Decimal
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from cart.cart import Cart
from customers.models import CustomerProfile
from inventory.services import record_stock_movement
from products.models import Product

from .forms import CheckoutForm
from .models import MpesaPayment, Order, OrderItem
from .mpesa import MpesaError, initiate_stk_push, query_stk_status

# The session remembers the customer's latest order, so guests can see their confirmation
LAST_ORDER_SESSION_KEY = 'last_order_id'


class StockProblem(Exception):
    """Raised when something in the cart can't be sold any more."""


class PaymentAmountProblem(Exception):
    """Raised when an order total cannot be charged exactly through STK Push."""


def _checkout_context(form, cart):
    return {
        'form': form,
        'items': list(cart),
        'total': cart.get_total_price(),
    }


@transaction.atomic
def place_order(request, form, cart):
    """Create the order and reduce stock. All of it happens, or none of it does.

    If anything goes wrong halfway, the whole transaction is undone,
    so we never end up with half an order or wrong stock numbers.
    """
    quantities = {int(product_id): qty for product_id, qty in cart.cart.items()}

    # Lock these products while we work, so two customers can't take the last item at once
    products = Product.objects.select_for_update().filter(
        id__in=quantities.keys(), is_available=True
    )
    found = {product.id: product for product in products}

    # 1. Check every item against the CURRENT stock and price
    total = Decimal('0')
    for product_id, qty in quantities.items():
        product = found.get(product_id)
        if product is None:
            raise StockProblem('An item in your cart is no longer available. Please review your cart.')
        if qty > product.stock_quantity:
            raise StockProblem(
                f'Sorry, we only have {product.stock_quantity} of {product.name} left. '
                f'Please update your cart.'
            )
        total += product.price * qty

    if form.cleaned_data.get('payment_method') == 'mpesa':
        if total <= 0 or total != total.to_integral_value():
            raise PaymentAmountProblem(
                'M-Pesa requires a positive whole-number KSh total. Please contact us to adjust this order.'
            )

    # 2. Create the order
    order = form.save(commit=False)
    order.total = total
    if request.user.is_authenticated:
        order.user = request.user
    order.save()

    # 3. Save each line (with a copy of the name and price) and reduce stock
    for product_id, qty in quantities.items():
        product = found[product_id]
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            price=product.price,
            quantity=qty,
        )
        record_stock_movement(
            product=product,
            quantity_change=-qty,
            reason='sale',
            notes=f'Order {order.order_number}',
            order_item=order_item,
        )

    return order


@transaction.atomic
def _finish_unsuccessful_payment(payment, status, result_code, description):
    payment = MpesaPayment.objects.select_for_update().select_related('order').get(pk=payment.pk)
    if payment.status != 'pending':
        return

    order = Order.objects.select_for_update().get(pk=payment.order_id)
    for item in order.items.select_related('product'):
        if item.product_id:
            record_stock_movement(
                product=item.product,
                quantity_change=item.quantity,
                reason='adjustment',
                notes=f'M-Pesa {status} for {order.order_number}',
                order_item=item,
            )

    payment.status = status
    payment.result_code = str(result_code)
    payment.result_description = description[:255]
    payment.save(update_fields=[
        'status', 'result_code', 'result_description', 'updated_at',
    ])
    order.status = 'cancelled'
    order.save(update_fields=['status', 'updated_at'])


def _callback_metadata(callback):
    metadata = callback.get('CallbackMetadata', {})
    items = metadata.get('Item', []) if isinstance(metadata, dict) else []
    return {
        item.get('Name'): item.get('Value')
        for item in items
        if isinstance(item, dict) and isinstance(item.get('Name'), str)
    }


@csrf_exempt
@require_POST
def mpesa_callback(request):
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid callback.'}, status=400)

    body = payload.get('Body') if isinstance(payload, dict) else None
    stk_callback = body.get('stkCallback') if isinstance(body, dict) else None
    if not isinstance(stk_callback, dict):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid callback.'}, status=400)

    checkout_id = stk_callback.get('CheckoutRequestID')
    if not isinstance(checkout_id, str) or not checkout_id:
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Missing checkout reference.'}, status=400)

    payment = MpesaPayment.objects.filter(checkout_request_id=checkout_id).first()
    if payment is None:
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Unknown checkout reference.'}, status=404)
    if payment.status != 'pending':
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Callback already processed.'})

    result_code = stk_callback.get('ResultCode')
    merchant_id = stk_callback.get('MerchantRequestID')
    if result_code is None or str(merchant_id) != payment.merchant_request_id:
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Payment reference mismatch.'}, status=400)

    try:
        verified_result = query_stk_status(checkout_id)
    except MpesaError:
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Payment verification temporarily unavailable.'}, status=503)
    if verified_result != str(result_code):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Payment result could not be verified.'}, status=409)

    if str(result_code) == '0':
        metadata = _callback_metadata(stk_callback)
        try:
            amount = Decimal(str(metadata['Amount']))
        except (KeyError, ArithmeticError, ValueError):
            return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid payment details.'}, status=400)

        phone = ''.join(char for char in str(metadata.get('PhoneNumber', '')) if char.isdigit())
        receipt = metadata.get('MpesaReceiptNumber')
        if (
            amount != payment.amount
            or phone != payment.phone_number
            or not isinstance(receipt, str)
            or not receipt.strip()
        ):
            return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Payment details do not match.'}, status=400)

        with transaction.atomic():
            locked_payment = MpesaPayment.objects.select_for_update().get(pk=payment.pk)
            if locked_payment.status == 'pending':
                locked_payment.status = 'successful'
                locked_payment.receipt_number = receipt.strip()
                locked_payment.result_code = '0'
                locked_payment.result_description = str(stk_callback.get('ResultDesc', 'Payment received'))[:255]
                locked_payment.save(update_fields=[
                    'status', 'receipt_number', 'result_code',
                    'result_description', 'updated_at',
                ])
    else:
        status = 'cancelled' if str(result_code) == '1032' else 'failed'
        _finish_unsuccessful_payment(
            payment,
            status,
            result_code,
            str(stk_callback.get('ResultDesc', 'Payment was not completed')),
        )

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Callback processed.'})


@require_GET
def payment_status(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    placed_in_this_session = request.session.get(LAST_ORDER_SESSION_KEY) == order.pk
    owns_the_order = request.user.is_authenticated and order.user_id == request.user.id
    if not (placed_in_this_session or owns_the_order):
        raise Http404('Order not found.')

    payment = order.mpesa_payments.first()
    if payment is None:
        return JsonResponse({'status': 'not_required'})
    return JsonResponse({
        'status': payment.status,
        'message': payment.get_status_display(),
        'receipt': payment.receipt_number,
    })


def checkout(request):
    """The checkout page: delivery details on the left, order summary on the right."""
    cart = Cart(request)
    items = list(cart)

    if not items:
        messages.warning(request, 'Your cart is empty. Add something before checking out.')
        return redirect('cart:detail')

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            use_mpesa = form.cleaned_data['payment_method'] == 'mpesa'

            try:
                with transaction.atomic():
                    order = place_order(request, form, cart)
                    payment = None
                    if use_mpesa:
                        payment = MpesaPayment.objects.create(
                            order=order,
                            phone_number=form.cleaned_data['mpesa_phone'],
                            amount=order.total,
                        )
                    if request.user.is_authenticated:
                        CustomerProfile.objects.update_or_create(
                            user=request.user,
                            defaults={
                                'phone': order.phone,
                                'address': order.address,
                                'city': order.city,
                            },
                        )
            except StockProblem as problem:
                messages.error(request, str(problem))
                return redirect('cart:detail')
            except PaymentAmountProblem as problem:
                form.add_error(None, str(problem))
                return render(request, 'sales/checkout.html', _checkout_context(form, cart))

            if payment is not None:
                try:
                    merchant_id, checkout_id = initiate_stk_push(payment)
                except MpesaError as error:
                    _finish_unsuccessful_payment(
                        payment,
                        'failed',
                        'initiation_failed',
                        str(error),
                    )
                    form.add_error(None, str(error))
                    return render(request, 'sales/checkout.html', _checkout_context(form, cart))

                payment.merchant_request_id = merchant_id
                payment.checkout_request_id = checkout_id
                payment.save(update_fields=[
                    'merchant_request_id', 'checkout_request_id', 'updated_at',
                ])

            cart.clear()
            request.session[LAST_ORDER_SESSION_KEY] = order.pk
            return redirect('sales:success', order_id=order.pk)
    else:
        # Save logged-in customers some typing
        initial = {}
        if request.user.is_authenticated:
            initial['full_name'] = request.user.get_full_name() or request.user.first_name
            initial['email'] = request.user.email
            profile = getattr(request.user, 'customer_profile', None)
            if profile is not None:
                initial.update({
                    'phone': profile.phone,
                    'address': profile.address,
                    'city': profile.city,
                })
        form = CheckoutForm(initial=initial)

    return render(request, 'sales/checkout.html', _checkout_context(form, cart))


def order_success(request, order_id):
    """The thank-you page. Only the customer who placed the order can see it."""
    order = get_object_or_404(Order, pk=order_id)

    placed_in_this_session = request.session.get(LAST_ORDER_SESSION_KEY) == order.pk
    owns_the_order = request.user.is_authenticated and order.user_id == request.user.id
    if not (placed_in_this_session or owns_the_order):
        raise Http404('Order not found.')

    payment = order.mpesa_payments.first()
    return render(request, 'sales/order_success.html', {
        'order': order,
        'payment': payment,
    })


@login_required
def order_list(request):
    """'My orders': every order placed while this customer was logged in."""
    orders = Order.objects.filter(user=request.user).prefetch_related('items')
    return render(request, 'sales/order_list.html', {'orders': orders})


@login_required
def order_detail(request, order_id):
    """One of the customer's own orders. Other people's orders show 'not found'."""
    order = get_object_or_404(
        Order.objects.prefetch_related('items'),
        pk=order_id,
        user=request.user,
    )
    return render(request, 'sales/order_detail.html', {'order': order})