from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0017_saleordersnapshot_pre_order_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="saleordersnapshot",
            name="kara_order_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="GUID کارا برای چاپ پیش‌فاکتور (SaleOrderAllGrid.OrderId)",
                max_length=36,
            ),
        ),
    ]
