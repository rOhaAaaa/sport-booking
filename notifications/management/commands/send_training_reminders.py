from django.core.management.base import BaseCommand, CommandError

from notifications.services import ReminderService


class Command(BaseCommand):
    help = "Створює нагадування про майбутні підтверджені заняття."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Період до початку заняття в годинах: від 1 до 720.",
        )

    def handle(self, *args, **options):
        hours = options["hours"]

        if not 1 <= hours <= 720:
            raise CommandError(
                "Параметр --hours має бути від 1 до 720."
            )

        created_count = ReminderService.create_upcoming_reminders(
            hours=hours,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Створено нагадувань: {created_count}"
            )
        )