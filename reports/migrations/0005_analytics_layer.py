# Generated manually for analytics layer

from django.db import migrations, models
import django.db.models.deletion
import reports.constants


def populate_daily_business_metric_dates(apps, schema_editor):
    DailyBusinessMetric = apps.get_model("reports", "DailyBusinessMetric")
    from reports.services.dates import parse_business_date

    for row in DailyBusinessMetric.objects.all().iterator():
        if row.business_date:
            continue
        parsed = parse_business_date(row.metric_date)
        if parsed:
            row.business_date = parsed
            row.save(update_fields=["business_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0004_user_kara_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailybusinessmetric",
            name="business_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="dailybusinessmetric",
            name="average_order_value",
            field=models.DecimalField(decimal_places=0, default=0, max_digits=20),
        ),
        migrations.AddField(
            model_name="dailybusinessmetric",
            name="total_reversion",
            field=models.DecimalField(decimal_places=0, default=0, max_digits=20),
        ),
        migrations.AddField(
            model_name="dailybusinessmetric",
            name="reversion_rate",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.RunPython(
            populate_daily_business_metric_dates,
            migrations.RunPython.noop,
        ),
        migrations.AlterModelOptions(
            name="dailybusinessmetric",
            options={
                "ordering": ["-metric_date", "-business_date"],
                "verbose_name": "شاخص روزانه کسب‌وکار",
                "verbose_name_plural": "شاخص‌های روزانه کسب‌وکار",
            },
        ),
        migrations.AddField(
            model_name="managementalert",
            name="rule_key",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="managementalert",
            name="entity_type",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="managementalert",
            name="entity_code",
            field=models.CharField(blank=True, db_index=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="managementalert",
            name="period",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
        migrations.AlterUniqueTogether(
            name="managementalert",
            unique_together={("rule_key", "entity_type", "entity_code", "period")},
        ),
        migrations.CreateModel(
            name="AnalyticsPeriod",
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
                ("report_key", models.CharField(db_index=True, max_length=100)),
                ("business_date", models.DateField(db_index=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("running", "running"),
                            ("success", "success"),
                            ("partial", "partial"),
                            ("failed", "failed"),
                            ("cancelled", "cancelled"),
                        ],
                        db_index=True,
                        default=reports.constants.SyncStatus["PENDING"],
                        max_length=20,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="analytics_periods",
                        to="reports.karareportsnapshot",
                    ),
                ),
            ],
            options={
                "verbose_name": "دوره تحلیلی",
                "verbose_name_plural": "دوره‌های تحلیلی",
                "ordering": ["-business_date", "report_key"],
                "unique_together": {("report_key", "business_date")},
            },
        ),
        migrations.CreateModel(
            name="SalespersonDailyMetric",
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
                ("business_date", models.DateField(db_index=True)),
                ("personnel_code", models.CharField(db_index=True, max_length=50)),
                ("personnel_name", models.CharField(blank=True, default="", max_length=255)),
                (
                    "supervisor_code",
                    models.CharField(blank=True, db_index=True, default="", max_length=50),
                ),
                ("supervisor_name", models.CharField(blank=True, default="", max_length=255)),
                (
                    "total_sale",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                (
                    "total_pure_sale",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                ("final_order_count", models.IntegerField(default=0)),
                ("preorder_count", models.IntegerField(default=0)),
                (
                    "average_order_value",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                (
                    "sale_reversion",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                (
                    "distribution_reversion",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                (
                    "reversion_rate",
                    models.DecimalField(decimal_places=2, default=0, max_digits=8),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("calculated_at", models.DateTimeField(auto_now=True)),
                (
                    "snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="salesperson_daily_metrics",
                        to="reports.karareportsnapshot",
                    ),
                ),
            ],
            options={
                "verbose_name": "شاخص روزانه فروشنده",
                "verbose_name_plural": "شاخص‌های روزانه فروشنده",
                "ordering": ["-business_date", "-total_sale"],
                "unique_together": {("business_date", "personnel_code")},
            },
        ),
        migrations.CreateModel(
            name="SupervisorDailyMetric",
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
                ("business_date", models.DateField(db_index=True)),
                ("supervisor_code", models.CharField(db_index=True, max_length=50)),
                ("supervisor_name", models.CharField(blank=True, default="", max_length=255)),
                (
                    "total_sale",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                (
                    "total_pure_sale",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                ("final_order_count", models.IntegerField(default=0)),
                ("salesperson_count", models.IntegerField(default=0)),
                ("active_salesperson_count", models.IntegerField(default=0)),
                (
                    "average_sale_per_person",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                (
                    "reversion_rate",
                    models.DecimalField(decimal_places=2, default=0, max_digits=8),
                ),
                (
                    "snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="supervisor_daily_metrics",
                        to="reports.karareportsnapshot",
                    ),
                ),
            ],
            options={
                "verbose_name": "شاخص روزانه سرپرست",
                "verbose_name_plural": "شاخص‌های روزانه سرپرست",
                "ordering": ["-business_date", "-total_sale"],
                "unique_together": {("business_date", "supervisor_code")},
            },
        ),
        migrations.CreateModel(
            name="RegionDailyMetric",
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
                ("business_date", models.DateField(db_index=True)),
                (
                    "dimension_type",
                    models.CharField(
                        choices=[
                            ("city", "city"),
                            ("zone", "zone"),
                            ("product_group", "product_group"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("dimension_code", models.CharField(db_index=True, max_length=120)),
                ("dimension_name", models.CharField(blank=True, default="", max_length=255)),
                (
                    "total_sale",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                (
                    "pure_sale",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                ("order_count", models.IntegerField(default=0)),
                (
                    "reversion_amount",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                (
                    "snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="region_daily_metrics",
                        to="reports.karareportsnapshot",
                    ),
                ),
            ],
            options={
                "verbose_name": "شاخص روزانه منطقه",
                "verbose_name_plural": "شاخص‌های روزانه منطقه",
                "ordering": ["-business_date", "-pure_sale"],
                "unique_together": {("business_date", "dimension_type", "dimension_code")},
            },
        ),
        migrations.CreateModel(
            name="BackfillRun",
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
                ("from_date", models.DateField()),
                ("to_date", models.DateField()),
                ("reports", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("running", "running"),
                            ("success", "success"),
                            ("partial", "partial"),
                            ("failed", "failed"),
                            ("cancelled", "cancelled"),
                        ],
                        db_index=True,
                        default=reports.constants.SyncStatus["PENDING"],
                        max_length=20,
                    ),
                ),
                ("current_date", models.DateField(blank=True, null=True)),
                ("completed_dates", models.JSONField(blank=True, default=list)),
                ("dry_run", models.BooleanField(default=False)),
                ("delay_seconds", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "اجرای بک‌فیل",
                "verbose_name_plural": "اجراهای بک‌فیل",
                "ordering": ["-created_at"],
            },
        ),
    ]
