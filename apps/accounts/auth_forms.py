"""
allauth form overrides. Kept apart from ``forms.py`` because allauth imports
that module (ACCOUNT_SIGNUP_FORM_CLASS) while loading its own forms, so
importing allauth's forms from there would be circular.
"""

from allauth.account.forms import LoginForm as AllauthLoginForm


class LoginForm(AllauthLoginForm):
    """allauth's login form without the "Forgot your password?" help text on the
    password field; the template shows that link once, next to "Remember me"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].help_text = ""
