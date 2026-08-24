from django.core.exceptions import ValidationError

BLOCKED_PASSWORDS = {
    "passwordpassword",
    "qwertyqwerty123",
    "tandemtandem123",
}


class LocalPasswordBlocklistValidator:
    def validate(self, password, user=None):
        if password.casefold().strip() in BLOCKED_PASSWORDS:
            raise ValidationError("This password is blocked.", code="password_blocked")

    def get_help_text(self):
        return "Your password must not be in the local blocked-password list."
