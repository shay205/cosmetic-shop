from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.shortcuts import render
from django.urls import reverse

from customers.models import CustomerProfile

from .forms import RegisterForm


User = get_user_model()
EMAIL_VERIFICATION_SALT = 'accounts.email_verification'


def _send_verification_email(request, user):
    token = signing.dumps(
        {'user_id': user.pk, 'email': user.email},
        salt=EMAIL_VERIFICATION_SALT,
    )
    verification_url = request.build_absolute_uri(
        reverse('accounts:verify_email', kwargs={'token': token})
    )
    send_mail(
        'Verify your Glow Beauty email address',
        f'Confirm your email address by opening this link:\n\n{verification_url}\n\n'
        'This link expires in 24 hours.',
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def register(request):
    """Let a new customer create an account using our RegisterForm."""
    # Customers who are already logged in don't need to register again
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            CustomerProfile.objects.get_or_create(user=user)
            _send_verification_email(request, user)
            return render(request, 'accounts/verification.html', {'sent': True})
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def verify_email(request, token):
    try:
        data = signing.loads(token, salt=EMAIL_VERIFICATION_SALT, max_age=60 * 60 * 24)
        user = User.objects.filter(pk=data['user_id'], email__iexact=data['email']).first()
    except (signing.BadSignature, KeyError, TypeError):
        return render(request, 'accounts/verification.html', {'verified': False})

    if user is None:
        return render(request, 'accounts/verification.html', {'verified': False})
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=['is_active'])
    return render(request, 'accounts/verification.html', {'verified': True})