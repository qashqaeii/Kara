"""Provision bot login credentials for synced visitors."""

from django.core.management.base import BaseCommand

from reports.bot.services.credentials import BotCredentialService


class Command(BaseCommand):
    help = "Create bot login credentials for visitors synced from Kara"

    def add_arguments(self, parser):
        parser.add_argument(
            "--personnel-code",
            dest="personnel_code",
            help="Provision a single visitor by personnel code",
        )
        parser.add_argument(
            "--password",
            help="Override default password (default: same as personnel code)",
        )
        parser.add_argument(
            "--generate",
            action="store_true",
            help="Generate a random numeric password instead of personnel code",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="provision_all",
            help="Provision all synced visitors missing credentials",
        )
        parser.add_argument(
            "--name",
            default="",
            help="Display name (only with --personnel-code)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List synced visitors without creating credentials",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            visitors = BotCredentialService.synced_visitors()
            if not visitors:
                self.stderr.write("هیچ ویزیتوری در دیتابیس sync‌شده یافت نشد.")
                return
            self.stdout.write(f"{'کد پرسنلی':<16} {'نام':<30} {'اعتبار'}")
            for v in visitors:
                has = "✓" if BotCredentialService.credential_exists(v["code"]) else "—"
                self.stdout.write(f"{v['code']:<16} {v['name'][:28]:<30} {has}")
            return

        if options["personnel_code"]:
            result = BotCredentialService.provision(
                options["personnel_code"],
                display_name=options["name"],
                password=options.get("password"),
                generate=options["generate"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"{'ایجاد شد' if result.created else 'بروزرسانی شد'}: "
                    f"{result.personnel_code} ({result.display_name})"
                )
            )
            if result.password:
                self.stdout.write(f"رمز عبور: {result.password}")
            return

        if not options["provision_all"]:
            self.stderr.write("--all یا --personnel-code الزامی است.")
            return

        results = BotCredentialService.provision_from_sync(
            password=options.get("password"),
            generate=options["generate"],
            only_missing=True,
        )
        if not results:
            self.stdout.write("همه ویزیتورها از قبل credential دارند یا داده sync نیست.")
            return

        self.stdout.write(self.style.SUCCESS(f"{len(results)} ویزیتور آماده شد:"))
        for r in results:
            line = f"  {r.personnel_code:<16} {r.display_name[:24]:<24}"
            if r.password:
                line += f"  رمز: {r.password}"
            self.stdout.write(line)
