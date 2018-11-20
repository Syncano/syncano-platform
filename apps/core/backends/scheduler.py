# coding=UTF8

import json

from redbeat import schedulers


class RedBeatSchedulerEntry(schedulers.RedBeatSchedulerEntry):
    def save(self):
        definition = {
            'name': self.name,
            'task': self.task,
            'args': self.args,
            'kwargs': self.kwargs,
            'options': self.options,
            'schedule': self.schedule,
            'enabled': self.enabled,
        }
        with schedulers.redis(self.app).pipeline() as pipe:
            pipe.hset(self.key, 'definition', json.dumps(definition, cls=schedulers.RedBeatJSONEncoder))
            pipe.zadd(self.app.redbeat_conf.schedule_key, {self.key: self.score})
            pipe.execute()

        return self

    def _next_instance(self, last_run_at=None, only_update_last_run_at=False):
        entry = super(schedulers.RedBeatSchedulerEntry, self)._next_instance(last_run_at=last_run_at)

        if only_update_last_run_at:
            # rollback the update to total_run_count
            entry.total_run_count = self.total_run_count

        meta = {
            'last_run_at': entry.last_run_at,
            'total_run_count': entry.total_run_count,
        }

        with schedulers.redis(self.app).pipeline() as pipe:
            pipe.hset(self.key, 'meta', json.dumps(meta, cls=schedulers.RedBeatJSONEncoder))
            pipe.zadd(self.app.redbeat_conf.schedule_key, {entry.key: entry.score})
            pipe.execute()
    __next__ = next = _next_instance

    def reschedule(self, last_run_at=None):
        self.last_run_at = last_run_at or self._default_now()
        meta = {
            'last_run_at': self.last_run_at,
        }
        with schedulers.redis(self.app).pipeline() as pipe:
            pipe.hset(self.key, 'meta', json.dumps(meta, cls=schedulers.RedBeatJSONEncoder))
            pipe.zadd(self.app.redbeat_conf.schedule_key, {self.key, self.score})
            pipe.execute()


class RedBeatScheduler(schedulers.RedBeatScheduler):
    Entry = RedBeatSchedulerEntry
