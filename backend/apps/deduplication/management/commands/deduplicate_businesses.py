import json
from contextlib import nullcontext
from itertools import batched

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.deduplication.services import resolve_normalized_record
from apps.sources.models import NormalizedSourceRecord


class Command(BaseCommand):
    help = "Resolve existing normalized records into canonical businesses (manual backfill)."

    def add_arguments(self, parser):
        parser.add_argument("--owner", type=int, help="Limit to this user's integer primary key.")
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the same resolver, then roll back all changes and resolution events.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if batch_size <= 0:
            raise CommandError("--batch-size must be a positive integer.")

        records = NormalizedSourceRecord.objects.filter(business_membership__isnull=True)
        if options["owner"] is not None:
            records = records.filter(source_record__campaign__created_by_id=options["owner"])
        records = records.order_by("source_record__campaign__created_by_id", "normalized_at", "id")
        summary = {
            "examined": 0,
            "created_businesses": 0,
            "automatic_attachments": 0,
            "pending_candidates": 0,
            "already_resolved": 0,
            "failures": 0,
        }
        dry_run = options["dry_run"]
        with transaction.atomic() if dry_run else nullcontext():
            record_ids = records.values_list("id", flat=True).iterator(chunk_size=batch_size)
            try:
                for batch in batched(record_ids, batch_size):
                    # Real runs commit once per batch. Dry runs retain the same
                    # batch/savepoint flow inside their rollback-only transaction.
                    with transaction.atomic():
                        for record_id in batch:
                            summary["examined"] += 1
                            try:
                                # Catch only outside this savepoint: even failures
                                # after resolver writes must roll back the whole row.
                                with transaction.atomic():
                                    outcome = resolve_normalized_record(record_id)
                            except Exception as error:
                                if transaction.get_rollback():
                                    # The savepoint could not restore a usable
                                    # transaction; abort so the entire batch rolls back.
                                    raise
                                summary["failures"] += 1
                                self.stderr.write(f"Failed {record_id}: {type(error).__name__}")
                                continue
                            if outcome.action == "seeded":
                                summary["created_businesses"] += 1
                            elif outcome.action in ("automatic", "source_identity"):
                                summary["automatic_attachments"] += 1
                            elif outcome.action == "already_resolved":
                                summary["already_resolved"] += 1
                            summary["pending_candidates"] += len(outcome.candidate_ids)
            finally:
                record_ids.close()
                if dry_run:
                    # Discard both database writes and deferred on_commit events.
                    transaction.set_rollback(True)
        self.stdout.write(json.dumps(summary))
