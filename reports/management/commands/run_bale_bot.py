"""Run Bale messenger bot."""

from django.core.management.base import BaseCommand

from reports.bot.runner import run_polling


class Command(BaseCommand):
    help = "Start the Bale visitor bot (long polling)"

    def handle(self, *args, **options):
        run_polling()
