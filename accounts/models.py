from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Користувач",
    )
    phone = models.CharField(
        "Телефон",
        max_length=25,
        blank=True,
    )
    photo = models.ImageField(
        "Фото",
        upload_to="profiles/",
        blank=True,
    )
    preferences = models.TextField(
        "Спортивні вподобання",
        blank=True,
    )

    class Meta:
        verbose_name = "Профіль користувача"
        verbose_name_plural = "Профілі користувачів"

    def __str__(self):
        return f"Профіль {self.user.get_username()}"