from django.db.transaction import Atomic
from django.db import connections, DEFAULT_DB_ALIAS
from .signals import (
    pre_enter_atomic_block,
    post_enter_atomic_block,
    pre_exit_atomic_block,
    post_exit_atomic_block,
)


def get_connection(using=None):
    if using is None:
        using = DEFAULT_DB_ALIAS
    return connections[using]


# Monkey-patch django.db.transaction.Atomic on first load.
if not hasattr(Atomic, '_djts_patched'):
    original_atomic_init = Atomic.__init__
    original_atomic_enter = Atomic.__enter__
    original_atomic_exit = Atomic.__exit__

    def atomic_init(self, *args, **kwargs):
        original_atomic_init(self, *args, **kwargs)
        self._djts_outermost_stack = []

    def atomic_enter(self):
        connection = get_connection(self.using)

        outermost = not connection.in_atomic_block
        self._djts_outermost_stack.append(outermost)

        pre_enter_atomic_block.send(sender=Atomic,
                                    using=self.using,
                                    outermost=outermost,
                                    savepoint=self.savepoint)

        result = original_atomic_enter(self)

        post_enter_atomic_block.send(sender=None,
                                     using=self.using,
                                     outermost=outermost,
                                     savepoint=self.savepoint)

        return result

    def atomic_exit(self, exc_type, exc_value, traceback):
        connection = get_connection(self.using)

        successful = exc_type is None and not connection.needs_rollback
        outermost = self._djts_outermost_stack.pop()

        pre_exit_atomic_block.send(sender=None,
                                   using=self.using,
                                   outermost=outermost,
                                   savepoint=self.savepoint,
                                   successful=successful)

        try:
            result = original_atomic_exit(self, exc_type, exc_value, traceback)
        except:
            post_exit_atomic_block.send(sender=None,
                                        using=self.using,
                                        outermost=outermost,
                                        savepoint=self.savepoint,
                                        successful=False)
            raise

        post_exit_atomic_block.send(sender=None,
                                    using=self.using,
                                    outermost=outermost,
                                    savepoint=self.savepoint,
                                    successful=successful)

        return result

    Atomic._djts_patched = True
    Atomic.__init__ = atomic_init
    Atomic.__enter__ = atomic_enter
    Atomic.__exit__ = atomic_exit
