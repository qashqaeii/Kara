# Generated manually for bot user notifications inbox

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0012_bot_visitor_credential"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BotUserNotification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("bale_user_id", models.BigIntegerField(db_index=True)),
                ("category", models.CharField(db_index=True, max_length=30)),
                ("event_type", models.CharField(db_index=True, max_length=50)),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField()),
                (
                    "entity_type",
                    models.CharField(blank=True, default="", max_length=50),
                ),
                (
                    "entity_code",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=100
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("pushed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bot_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "اعلان کاربر ربات",
                "verbose_name_plural": "اعلان‌های کاربران ربات",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="botusernotification",
            index=models.Index(
                fields=["bale_user_id", "is_read", "-created_at"],
                name="reports_bot_bale_us_8f3a21_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="botusernotification",
            index=models.Index(
                fields=["bale_user_id", "category", "is_read"],
                name="reports_bot_bale_us_4c9e12_idx",
            ),
        ),
    ]
