from typing import cast

from django.conf import settings
from django.contrib.auth import (
    authenticate,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth import (
    login as django_login,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import generics, serializers, status
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.views import PrivateAPIView, PrivateResponseMixin, PublicAPIView

from .auth_services import (
    activate_account,
    grant,
    invalidate_user_sessions,
    issue_invitation,
    issue_password_reset,
    login_is_limited,
    record_auth_event,
    record_login_failure,
    request_ip,
    reset_password,
)
from .delivery import SMTPAuthDelivery
from .managers import UserManager
from .models import AccessGrant, User
from .permissions import HasMessengerAccess, IsPlatformAdmin
from .serializers import (
    AccountSerializer,
    GrantInputSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordPairSerializer,
    PasswordResetRequestSerializer,
    PlatformUserCreateSerializer,
    PlatformUserUpdateSerializer,
)


class MeView(PrivateAPIView):
    serializer_class = MeSerializer

    def get(self, request):
        return Response(self.serializer_class(request.user).data)


class CsrfView(PublicAPIView):
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")  # ty: ignore[invalid-argument-type]
class LoginView(PublicAPIView):
    serializer_class = LoginSerializer

    def post(self, request):
        payload = self.serializer_class(data=request.data)
        payload.is_valid(raise_exception=True)
        username = payload.validated_data["username"]
        ip = request_ip(request)
        if login_is_limited(username, ip):
            record_auth_event(request, "auth.login.rate_limited", username=username)
            raise Throttled(detail="Too many login attempts. Try again later.")
        user = cast(
            User | None,
            authenticate(request, username=username, password=payload.validated_data["password"]),
        )
        if user is None or not AccessGrant.objects.filter(user=user).exists():
            record_login_failure(username, ip)
            record_auth_event(request, "auth.login.failed", username=username)
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Invalid username or password.",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        django_login(request, user)
        now = int(timezone.now().timestamp())
        request.session["auth_started_at"] = now
        request.session["auth_last_seen_at"] = now
        record_auth_event(request, "auth.login.success", user=user, username=username)
        return Response({"user": AccountSerializer(user).data, "csrf_token": get_token(request)})


class SessionView(PrivateResponseMixin, APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_active:
            return Response({"authenticated": False, "user": None})
        return Response({"authenticated": True, "user": AccountSerializer(request.user).data})


class LogoutView(PrivateAPIView):
    def post(self, request):
        user = request.user
        record_auth_event(request, "auth.logout", user=user, username=user.username)
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(PrivateAPIView):
    serializer_class = PasswordChangeSerializer

    def post(self, request):
        payload = self.serializer_class(data=request.data, context={"request": request})
        payload.is_valid(raise_exception=True)
        if not request.user.check_password(payload.validated_data["current_password"]):
            raise serializers.ValidationError({"current_password": "Current password is invalid."})
        request.user.set_password(payload.validated_data["new_password"])
        request.user.password_changed_at = timezone.now()
        request.user.save(update_fields=["password", "password_changed_at", "updated_at"])
        update_session_auth_hash(request, request.user)
        record_auth_event(
            request, "auth.password.changed", user=request.user, username=request.user.username
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")  # ty: ignore[invalid-argument-type]
class ActivateView(PublicAPIView):
    serializer_class = PasswordPairSerializer

    def post(self, request):
        payload = self.serializer_class(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            user = activate_account(**payload.validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        record_auth_event(request, "auth.invite.used", user=user, username=user.username)
        return Response({"status": "activated"})


@method_decorator(csrf_protect, name="dispatch")  # ty: ignore[invalid-argument-type]
class PasswordResetRequestView(PublicAPIView):
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        payload = self.serializer_class(data=request.data)
        payload.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=payload.validated_data["email"], is_active=True
        ).first()
        if user is not None and settings.AUTH_RECOVERY_MODE == "SMTP":
            _row, token = issue_password_reset(user)
            SMTPAuthDelivery().deliver(
                recipient=user.email,
                purpose="password reset",
                url=f"{settings.AUTH_PUBLIC_BASE_URL}/reset-password?token={token}",
            )
        record_auth_event(
            request,
            "auth.password.reset_requested",
            user=user,
            username=payload.validated_data["email"],
        )
        return Response({"detail": "If the account exists, instructions were sent."})


@method_decorator(csrf_protect, name="dispatch")  # ty: ignore[invalid-argument-type]
class PasswordResetConfirmView(PublicAPIView):
    serializer_class = PasswordPairSerializer

    def post(self, request):
        payload = self.serializer_class(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            user = reset_password(**payload.validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        record_auth_event(request, "auth.password.reset", user=user, username=user.username)
        return Response({"status": "password_reset"})


class PlatformUserListCreateView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        queryset = User.objects.select_related("org_unit").prefetch_related("access_grants")
        if search := request.query_params.get("search", "").strip():
            queryset = queryset.filter(
                Q(full_name__icontains=search) | Q(username__icontains=search)
            )
        return Response(AccountSerializer(queryset[:200], many=True).data)

    @transaction.atomic
    def post(self, request):
        payload = PlatformUserCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        values = dict(payload.validated_data)
        grants = values.pop("grants", [])
        manager = User.objects
        assert isinstance(manager, UserManager)
        user = manager.create_user(**values)
        for item in grants:
            grant(user, item["module"], item["role"], actor=request.user)
        record_auth_event(request, "auth.account.created", user=user, username=user.username)
        return Response(AccountSerializer(user).data, status=status.HTTP_201_CREATED)


class PlatformUserDetailView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsPlatformAdmin]

    def get_user(self, user_id):
        return generics.get_object_or_404(
            User.objects.prefetch_related("access_grants"), pk=user_id
        )

    def get(self, request, user_id):
        return Response(AccountSerializer(self.get_user(user_id)).data)

    @transaction.atomic
    def patch(self, request, user_id):
        user = self.get_user(user_id)
        payload = PlatformUserUpdateSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        if user == request.user and payload.validated_data.get("is_active") is False:
            raise serializers.ValidationError({"is_active": "You cannot disable your own account."})
        for field, value in payload.validated_data.items():
            setattr(user, field, value)
        user.save(update_fields=[*payload.validated_data, "updated_at"])
        if "is_active" in payload.validated_data:
            if not user.is_active:
                transaction.on_commit(lambda: invalidate_user_sessions(user.pk))
            record_auth_event(
                request,
                "auth.account.enabled" if user.is_active else "auth.account.disabled",
                user=user,
                username=user.username,
            )
        return Response(AccountSerializer(user).data)


class PlatformGrantView(PrivateAPIView):
    permission_classes = [IsPlatformAdmin]

    def _validated(self, module, role):
        payload = GrantInputSerializer(data={"module": module.upper(), "role": role.upper()})
        payload.is_valid(raise_exception=True)
        return payload.validated_data

    def put(self, request, user_id, module, role):
        values = self._validated(module, role)
        user = generics.get_object_or_404(User, pk=user_id)
        _row, created = grant(user, **values, actor=request.user)
        if created:
            record_auth_event(
                request,
                "auth.role.granted",
                user=user,
                username=user.username,
                metadata=values,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request, user_id, module, role):
        values = self._validated(module, role)
        user = generics.get_object_or_404(User, pk=user_id)
        if (
            user == request.user
            and values["module"] == AccessGrant.Module.PLATFORM
            and values["role"] == AccessGrant.Role.ADMIN
        ):
            raise serializers.ValidationError("You cannot revoke your own platform-admin grant.")
        deleted, _ = AccessGrant.objects.filter(user=user, **values).delete()
        if deleted:
            record_auth_event(
                request,
                "auth.role.revoked",
                user=user,
                username=user.username,
                metadata=values,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlatformInvitationView(PrivateAPIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, user_id):
        user = generics.get_object_or_404(User, pk=user_id, is_active=True)
        _row, token = issue_invitation(user, actor=request.user)
        record_auth_event(request, "auth.invite.created", user=user, username=user.username)
        return Response({"activation_url": f"/activate?token={token}"})


class PlatformPasswordResetView(PrivateAPIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, user_id):
        user = generics.get_object_or_404(User, pk=user_id, is_active=True)
        _row, token = issue_password_reset(user, actor=request.user)
        record_auth_event(
            request, "auth.password.reset_requested", user=user, username=user.username
        )
        return Response({"reset_url": f"/reset-password?token={token}"})


class MessengerAccessView(PrivateAPIView):
    permission_classes = [HasMessengerAccess]

    def get(self, request):
        return Response({"allowed": True, "implementation": "stage-7"})
