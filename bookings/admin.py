from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from loyalty.models import Membership

from .models import Booking, Payment
from .services import BookingCheckoutService


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "hall",
        "session",
        "membership",
        "starts_at",
        "ends_at",
        "total_price",
        "status",
    )
    list_filter = ("status",)
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "hall__name",
        "session__section__name",
    )
    list_select_related = (
        "user",
        "hall",
        "session",
        "membership",
    )
    actions = (
        "confirm_with_payment",
        "confirm_with_membership",
        "confirm_free",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly = [
            field.name
            for field in self.model._meta.fields
            if field.name != "membership"
        ]

        if obj is None or obj.status != Booking.Status.PENDING:
            readonly.append("membership")

        return tuple(readonly)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if obj is not None and "membership" in form.base_fields:
            form.base_fields["membership"].queryset = (
                Membership.objects.filter(
                    user_id=obj.user_id,
                    status=Membership.Status.ACTIVE,
                )
                .select_related("plan")
                .order_by("-valid_from", "-pk")
            )

        return form

    def _confirm_selected(self, request, queryset, settlement):
        confirmed_count = 0
        skipped_count = 0

        for booking in queryset.order_by("pk"):
            if booking.status == Booking.Status.CONFIRMED:
                skipped_count += 1
                continue

            kwargs = {
                "user": booking.user,
                "booking_id": booking.pk,
                "settlement": settlement,
            }

            if settlement == "payment":
                kwargs["payment_successful"] = True
            elif settlement == "membership":
                kwargs["membership_id"] = booking.membership_id

            try:
                BookingCheckoutService.confirm(**kwargs)
            except ValidationError as exc:
                self.message_user(
                    request,
                    (
                        f"Бронювання №{booking.pk}: "
                        + "; ".join(exc.messages)
                    ),
                    level=messages.ERROR,
                )
            else:
                confirmed_count += 1

        if confirmed_count:
            self.message_user(
                request,
                f"Підтверджено бронювань: {confirmed_count}.",
                level=messages.SUCCESS,
            )

        if skipped_count:
            self.message_user(
                request,
                (
                    "Уже підтверджені бронювання пропущено: "
                    f"{skipped_count}."
                ),
                level=messages.INFO,
            )

    @admin.action(
        description=(
            "Імітувати успішну оплату та підтвердити"
        ),
        permissions=["change"],
    )
    def confirm_with_payment(self, request, queryset):
        self._confirm_selected(
            request,
            queryset,
            settlement="payment",
        )

    @admin.action(
        description=(
            "Підтвердити через зазначений абонемент"
        ),
        permissions=["change"],
    )
    def confirm_with_membership(self, request, queryset):
        self._confirm_selected(
            request,
            queryset,
            settlement="membership",
        )

    @admin.action(
        description="Підтвердити безкоштовну послугу",
        permissions=["change"],
    )
    def confirm_free(self, request, queryset):
        self._confirm_selected(
            request,
            queryset,
            settlement="free",
        )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booking",
        "amount",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = (
        "booking__user__username",
        "booking__user__first_name",
        "booking__user__last_name",
    )
    list_select_related = (
        "booking",
        "booking__user",
    )
    readonly_fields = (
        "id",
        "booking",
        "amount",
        "status",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False