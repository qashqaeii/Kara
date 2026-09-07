# Generated manually for monthly_sale + stuff_group_sale detail fields

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0006_sale_orders_and_stuffs"),
    ]

    operations = [
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="partner_code",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="partner_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="partner_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="pure_sale_quantity",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="route",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="row_key",
            field=models.CharField(blank=True, db_index=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="stuff_code",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="stuff_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="sub_group_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="visitor_code",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="stuffgroupsalesnapshot",
            name="visitor_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddIndex(
            model_name="stuffgroupsalesnapshot",
            index=models.Index(fields=["stuff_code", "-last_seen_at"], name="reports_stu_stuff_c_idx"),
        ),
        migrations.AddConstraint(
            model_name="stuffgroupsalesnapshot",
            constraint=models.UniqueConstraint(
                fields=("snapshot", "row_key"),
                name="uniq_stuff_group_row_per_snapshot",
            ),
        ),
        migrations.CreateModel(
            name="MonthlyCompanySales",
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
                ("fiscal_year", models.PositiveIntegerField(db_index=True, unique=True)),
                ("monthly_totals", models.JSONField(blank=True, default=dict)),
                (
                    "total_ytd",
                    models.DecimalField(decimal_places=0, default=0, max_digits=20),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="monthly_company_sales",
                        to="reports.karareportsnapshot",
                    ),
                ),
            ],
            options={
                "verbose_name": "فروش ماهانه شرکت",
                "verbose_name_plural": "فروش ماهانه شرکت",
                "ordering": ["-fiscal_year"],
            },
        ),
        migrations.CreateModel(
            name="MonthlySaleDetailSnapshot",
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
                ("fiscal_year", models.PositiveIntegerField(db_index=True)),
                ("row_key", models.CharField(db_index=True, max_length=120)),
                ("partner_code", models.CharField(blank=True, default="", max_length=50)),
                ("partner_name", models.CharField(blank=True, default="", max_length=255)),
                ("visitor_code", models.CharField(blank=True, default="", max_length=50)),
                ("visitor_name", models.CharField(blank=True, default="", max_length=255)),
                (
                    "stuff_code",
                    models.CharField(blank=True, db_index=True, default="", max_length=50),
                ),
                ("stuff_name", models.CharField(blank=True, default="", max_length=255)),
                (
                    "stuff_group_name",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "stuff_sub_group_name",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "partner_zone_route",
                    models.CharField(blank=True, default="", max_length=512),
                ),
                ("monthly_totals", models.JSONField(blank=True, default=dict)),
                ("raw_data", models.JSONField(blank=True, default=dict)),
                (
                    "snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="monthly_sale_rows",
                        to="reports.karareportsnapshot",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["fiscal_year", "stuff_code"],
                        name="reports_mon_fiscal__idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("snapshot", "row_key"),
                        name="uniq_monthly_sale_row_per_snapshot",
                    )
                ],
            },
        ),
    ]
