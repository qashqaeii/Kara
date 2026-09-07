# Generated manually for phase A

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reports", "0003_professional_sync_layer"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserKaraIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("personnel_code", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("system_admin", "system_admin"),
                            ("executive_manager", "executive_manager"),
                            ("sales_manager", "sales_manager"),
                            ("sales_supervisor", "sales_supervisor"),
                            ("salesperson", "salesperson"),
                            ("viewer", "viewer"),
                            ("tv_display", "tv_display"),
                        ],
                        db_index=True,
                        default="viewer",
                        max_length=32,
                    ),
                ),
                (
                    "supervisor_code",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="برای سرپرست: کد سرپرست در Kara",
                        max_length=50,
                    ),
                ),
                ("allowed_city_codes", models.JSONField(blank=True, default=list)),
                ("allowed_zone_codes", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="kara_identity",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "هویت کاربر در کارا",
                "verbose_name_plural": "هویت‌های کاربر در کارا",
            },
        ),
    ]
