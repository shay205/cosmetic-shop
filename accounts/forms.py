from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class RegisterForm(UserCreationForm):
    """Sign-up form: Django's built-in form plus first name and email."""

    first_name = forms.CharField(max_length=150, required=True, label='First name')
    email = forms.EmailField(required=True, label='Email address')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('first_name', 'username', 'email')

    def clean_email(self):
        """Make sure no two customers share the same email address."""
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email