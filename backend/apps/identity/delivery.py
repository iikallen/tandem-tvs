from typing import Protocol


class AuthDeliveryAdapter(Protocol):
    def deliver(self, *, recipient: str, purpose: str, url: str) -> None: ...


class ConsoleAuthDelivery:
    """Development hook; callers return the URL instead of logging secrets."""

    def deliver(self, *, recipient: str, purpose: str, url: str) -> None:
        return None


class SMTPAuthDelivery:
    def deliver(self, *, recipient: str, purpose: str, url: str) -> None:
        from django.core.mail import send_mail

        send_mail(
            subject=f"Tandem: {purpose}",
            message=url,
            from_email=None,
            recipient_list=[recipient],
            fail_silently=False,
        )
