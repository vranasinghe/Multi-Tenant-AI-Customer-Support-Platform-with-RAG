# Database migration and recovery

## 1. Policy (proposed, awaiting approval: MIG-02)

**Treat a database that holds real data as forward-only.** Recover from a bad release with a
corrective forward migration, or restore a backup taken before the migration. Do not downgrade.

Why: revision `0007` is published and cannot be reversed without loss.

* `0006` requires every usage record to have a conversation. From `0007`, usage outlives deleted
  conversations, so after any deletion or retention purge a downgrade below `0007` fails as a whole.
* When it does succeed, it drops conversation events, unanswered questions, daily analytics,
  export records, and conversation status, satisfaction, handoff and latency fields.

Never delete usage or other rows to make an old constraint pass. Never edit `0007`.

Until the policy is approved or changed, one safeguard is in place and can be removed:
with `APP_ENV` `staging` or `production`, Alembic refuses any downgrade and rolls it back unless
`ALLOW_DESTRUCTIVE_DOWNGRADE=yes`. Local and test databases are not guarded.

## 2. Before a migration

`deploy/deploy.sh` runs a quiesced backup before it starts a new release over a running
install, and stops if the backup fails (`SKIP_BACKUP=1` overrides). By hand:

```bash
QUIESCE=1 bash deploy/backup.sh
```

Then copy `~/backups` off the server, and note the deployed Git revision. Keep
`.env.production` safely apart from the backups; they do not contain it.

## 3. When a release is bad

1. **Application fault, schema fine:** redeploy the previous revision if the matrix (§6) allows
   it for the current schema. No database change.
2. **Schema or data fault:** write a new revision (`0008`, ...) that corrects it. Test it on a
   restored copy of production first, then back up and deploy. Preferred in almost every case.
3. **Data destroyed or corrupted:** restore (§4). Everything written after the backup is lost.

## 4. Restore

Restore into **empty** volumes. `restore.sh` refuses anything else, so the damaged install stays
untouched for investigation until the copy is verified. Use a new project name:

```bash
COMPOSE_PROJECT_NAME=acs-restore bash deploy/restore.sh ~/backups <stamp>
```

Do not restore a dump by piping it into `psql` yourself. A new database grants the application
role every DML right on each table as it is created, and a dump never takes rights away, so tables
the source had protected become deletable. `restore.sh` removes those defaults first (the dump
brings the source's own back) and stops at the first error.

Stop the old project first if both would publish the same ports. Check out the application
revision that matches the backup's schema before restoring.

## 5. Verify a restore

`python -m app.cli verify-data` prints, without row contents: the schema revision, a row count
and hash per table (vectors included), RLS settings, policies, grants, functions, constraints,
indexes, and whether every stored original and live export exists with its recorded size.

```bash
docker compose -p acs-restore --env-file .env.production -f docker-compose.prod.yml up -d
docker compose -p acs-restore --env-file .env.production -f docker-compose.prod.yml \
  exec -T api python -m app.cli verify-data > restored.json
```

To compare with the source, run the same command there with `api`, `worker`, `maintenance` and
`beat` stopped (`run --rm --no-deps api ...`) and `diff` the two files. It must exit 0, and
`/readyz`, a sign-in, a transcript and a retrieval search must work. Then move traffic.

`scripts/ci/restore-rehearsal.sh` does all of this on disposable stacks and runs in CI.

## 6. Application and schema compatibility

| Application | Schema | Status |
|---|---|---|
| Current (Phase 7 and Milestone A) | `0007` | Supported and tested |
| Current | `0006` or older | Not supported: queries need `0007` columns. Migrate first |
| `db4d352` (Phase 7, before Milestone A) | `0007` | Same schema. Milestone A added no migration. Its beat sends the sweep to `default`, which its worker consumes |
| Before Phase 7 (`afe3552`) | `0007` | Not tested. Do not rely on it |

Rolling the application back across the maintenance queue: the older release has no
`maintenance` service. `docker compose up --remove-orphans` removes it; sweeps already queued on
`maintenance` expire after one interval.

## 7. Recovery point and recovery time

* **Recovery point:** the last backup. With the documented nightly cron, **up to 24 hours** of
  conversations, usage, documents and settings can be lost. There is no point-in-time recovery:
  `DATABASE.md` describes a 14-day PITR target that is **not implemented**.
* **Queued work:** Redis is not backed up. Jobs are rows in Postgres and the sweeper re-queues them.
* **Online backups** read the database before the files; an original removed in between is
  missing from the copy and `verify-data` reports it. `QUIESCE=1` avoids this, with downtime.
* **Deleted data** remains in backups until they are removed (7 days locally; off-server copies
  follow their own retention).
* **Recovery time** has only been measured on a tiny synthetic data set (see the Milestone A
  validation results). Rehearse with production-sized data before relying on it.
