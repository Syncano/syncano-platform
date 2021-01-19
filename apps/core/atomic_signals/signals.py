from django.dispatch import Signal

pre_enter_atomic_block = Signal(providing_args=['using',
                                                'outermost',
                                                'savepoint'])
post_enter_atomic_block = Signal(providing_args=['using',
                                                 'outermost',
                                                 'savepoint'])
pre_exit_atomic_block = Signal(providing_args=['using',
                                               'outermost',
                                               'savepoint',
                                               'successful'])
post_exit_atomic_block = Signal(providing_args=['using',
                                                'outermost',
                                                'savepoint',
                                                'successful'])
