"""Set or reset a visitor bot password."""

from django.core.management.base import BaseCommand, CommandError

from reports.bot.services.credentials import BotCredentialService


class Command(BaseCommand):
    help = "Set bot password for a visitor by personnel code"

    def add_arguments(self, parser):
        parser.add_argument("personnel_code", help="Visitor personnel code")
        parser.add_argument(
            "password",
            nargs="?",
            help="New bot password (default: same as personnel code)",
        )

    def handle(self, *args, **options):
        code = options["personnel_code"]
        password = options.get("password") or BotCredentialService.default_password(code)
        if len(password) < 4:
            raise CommandError("رمز عبور باید حداقل ۴ کاراکتر باشد.")
        try:
            cred = BotCredentialService.set_password(code, password)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"رمز ربات برای {cred.personnel_code} ({cred.display_name}) تنظیم شد."
            )
        )
