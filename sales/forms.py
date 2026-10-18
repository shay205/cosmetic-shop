import re

from django import forms

from .models import Order


class CheckoutForm(forms.ModelForm):
    """The delivery details a customer fills in at checkout."""

    payment_method = forms.ChoiceField(
        choices=[('delivery', 'Pay on delivery'), ('mpesa', 'M-Pesa')],
        initial='delivery',
        label='Payment method',
        required=False,
    )
    mpesa_phone = forms.CharField(
        required=False,
        max_length=20,
        label='M-Pesa phone number',
        widget=forms.TelInput(attrs={'placeholder': 'e.g. 0712 345 678', 'autocomplete': 'tel'}),
    )

    class Meta:
        model = Order
        fields = ['full_name', 'email', 'phone', 'address', 'city', 'notes']
        labels = {
            'full_name': 'Full name',
            'email': 'Email address',
            'phone': 'Phone number',
            'address': 'Delivery address',
            'city': 'Town / City',
            'notes': 'Delivery notes (optional)',
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_phone(self):
        """Accept normal phone formats, reject anything that can't be a phone number."""
        phone = self.cleaned_data['phone'].strip()
        digits = re.sub(r'\D', '', phone)   # keep only the digits
        if not re.fullmatch(r'[\d\s\-\+\(\)]+', phone) or not 9 <= len(digits) <= 15:
            raise forms.ValidationError(
                'Please enter a valid phone number, for example 0712 345 678.'
            )
        return phone

    def clean_mpesa_phone(self):
        phone = self.cleaned_data['mpesa_phone'].strip()
        if not phone:
            return ''

        digits = re.sub(r'\D', '', phone)
        if re.fullmatch(r'0[17]\d{8}', digits):
            return f'254{digits[1:]}'
        if re.fullmatch(r'254[17]\d{8}', digits):
            return digits
        if re.fullmatch(r'[17]\d{8}', digits):
            return f'254{digits}'
        raise forms.ValidationError(
            'Enter a valid Kenyan M-Pesa number, for example 0712 345 678.'
        )

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data['payment_method'] = cleaned_data.get('payment_method') or 'delivery'
        if cleaned_data['payment_method'] == 'mpesa' and not cleaned_data.get('mpesa_phone'):
            self.add_error('mpesa_phone', 'Enter the M-Pesa number to receive the payment prompt.')
        return cleaned_data